#! /usr/local/bin/python

# Copyright 2025 David Valeri
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
import sys
import time
import subprocess
import argparse
import signal
import os

from pybirdbuddy.birdbuddy.client import BirdBuddy
from pybirdbuddy.birdbuddy.feeder import FeederState
from astral import LocationInfo
from astral.sun import sun
from datetime import datetime, timedelta

RECOVERY_FILE_PATH = "/config/recovery"
TOKEN_FILE_PATH = "/config/tokens"
COOLDOWN_FILE_PATH = "/config/cooldown"

terminate = False

def main():
    global root
    global terminate

    parser = argparse.ArgumentParser(description="Description of your program")
    parser.add_argument('--username', type=str, required=True, help='BirdBuddy username')
    parser.add_argument('--password', type=str, required=True, help='BirdBuddy password')
    parser.add_argument('--feeder_name', type=str, required=True, help='Feeder name')
    parser.add_argument('--out_url', type=str, required=True, help='Output URL for ffmpeg')
    parser.add_argument('--log_level', type=str, default='INFO', help='Log level. Default INFO.')
    parser.add_argument(
        '--min_starting_battery_level',
        type=int,
        default=70,
        help='Minimum battery level to start streaming after entering recovery state. Default 70%.')
    parser.add_argument(
        '--min_battery_level',
        type=int,
        default=40,
        help='Battery level at which the stream is stopped and recovery state is entered. Default 40%.')
    parser.add_argument(
        '--output_codec',
        type=str,
        default='copy',
        help='ffmpeg codec for output encoding. Default "copy".')
    parser.add_argument(
        '--continuous',
        type=bool,
        default=True,
        help=(
            'If the program should run continuously, attempting to start / restart the stream repeatedly and '
            'streaming a splash screen if the real stream is unavailable, or if it should try just once. '
            'Default true.'
        )
    )
    parser.add_argument('--latitude', type=float, required=True, help='Latitude for location.')
    parser.add_argument('--longitude', type=float, required=True, help='Longitude for location.')
    parser.add_argument('--timezone', type=str, required=True, help='Timezone for location.')

    args = parser.parse_args()

    root.setLevel(args.log_level)

    city = LocationInfo("Home", "WhereItsAt", args.timezone, latitude=args.latitude, longitude=args.longitude)
    LOGGER.debug("Using %s for sunset calculations.", city)

    return_code = 0
    splash_ffmpeg_process = None
    while not terminate:

        LOGGER.info("Starting / Restarting stream.")

        if args.continuous:
            if (splash_ffmpeg_process is None or splash_ffmpeg_process.poll() is not None):
                splash_ffmpeg_process = run_splash_ffmpeg(args.out_url, args.output_codec, args.log_level)

                if (splash_ffmpeg_process is None or splash_ffmpeg_process.poll() is not None):
                    LOGGER.error("Error starting splash ffmpeg. Continuing anyway.")
                else:
                    LOGGER.info("Splash ffmpeg started.")

        return_code = run(args, city, splash_ffmpeg_process)

        if args.continuous:
            time.sleep(5)
        else:
            terminate = True

    stop_ffmpeg(splash_ffmpeg_process, "splash")

    LOGGER.info("Goodbye.")

    return return_code

def run(args, city, splash_ffmpeg_process):
    global terminate

    if is_in_cooldown():
        LOGGER.info("Cooldown period active. Skipping stream initialization.")
        return 1

    clear_cooldown()

    try:
        bb = init_bb(args)
    except Exception as e:
        LOGGER.error("Error initializing Bird Buddy: %s", e)
        return 2

    try:
        asyncio.run(bb.refresh())
        save_tokens(bb)
    except Exception as e:
        LOGGER.error("Error refreshing Bird Buddy: %s", e)
        return 3

    feeder = get_feeder_by_name(bb, args.feeder_name)
    if not feeder:
        LOGGER.error(
            "Feeder with name '%s' not found. Available feeders: %s",
            args.feeder_name,
            [feeder.name for feeder in bb.feeders.values()])
        return 4

    if feeder.state != FeederState.READY_TO_STREAM and feeder.state != FeederState.STREAMING:
        LOGGER.error("Feeder state, '%s', is not streaming or ready to stream.", feeder.state)
        if feeder.state in [FeederState.DEEP_SLEEP, FeederState.OFFLINE, FeederState.OFF_GRID, FeederState.OUT_OF_FEEDER]:
            set_cooldown()
        return 5

    if is_sleepy_time(city):
        LOGGER.info("Feeder is preparing to enter deep sleep state. Skipping stream initialization.")
        set_cooldown()
        return 6

    if feeder.battery.percentage < args.min_battery_level:
        LOGGER.error(
            "Battery level, %s, is less than %s.",
            feeder.battery.percentage,
            args.min_battery_level)
        set_recovery()
        set_cooldown()
        return 7

    if os.path.exists(RECOVERY_FILE_PATH):
        if feeder.battery.percentage < args.min_starting_battery_level:
            LOGGER.error(
                "Battery level, %s, is less than minimum required to start stream, %s.",
                feeder.battery.percentage,
                args.min_starting_battery_level)
            set_recovery()
            set_cooldown()
            return 8

    clear_recovery()

    result = asyncio.run(bb.watching_start(feeder.id))
    LOGGER.info("Birdbuddy stream started.")

    if terminate:
        LOGGER.info("Received termination signal. Skipping stream initialization.")
        return 0

    in_url = result["watching"]["streamUrl"]
    if in_url is None:
        LOGGER.error("Stream URL was empty.")
        set_cooldown()
        return 9

    stop_ffmpeg(splash_ffmpeg_process, "splash")

    restream_ffmpeg_process = run_restream_ffmpeg(
        in_url,
        args.out_url,
        args.output_codec,
        args.log_level)

    if restream_ffmpeg_process is None:
        return 10

    LOGGER.info("Restream ffmpeg started.")

    # Refresh stream every 30 seconds. Recheck feeder states every 5 minutes.
    while not terminate and restream_ffmpeg_process.poll() is None:
        i = 0
        while i < 10 and not terminate:
            j = 0
            while j < 6 and not terminate:
                time.sleep(5)
                j += 1

            try:
                refresh_result = asyncio.run(bb.watching_active_keep())
                if LOGGER.isEnabledFor(logging.DEBUG):
                    LOGGER.debug("Refreshed stream. %s", refresh_result)
                else:
                    LOGGER.info("Refreshed stream.",)
            except Exception as e:
                LOGGER.warning("Error refreshing stream: %s", e)
            i += 1

        try:
            asyncio.run(bb.refresh())
            save_tokens(bb)
        except Exception as e:
            LOGGER.warning("Error refreshing Bird Buddy: %s", e)

        if feeder.battery.percentage < args.min_battery_level:
            LOGGER.error(
                "Battery level, %s, is less than %s. Entering recovery state.",
                feeder.battery.percentage,
                args.min_battery_level)
            set_recovery()
            set_cooldown()
            break

        if is_sleepy_time(city):
            LOGGER.info("Stopping stream to allow feeder to enter deep sleep state.")
            break

    stop_ffmpeg(restream_ffmpeg_process, "restream")

    return 0

def init_bb(args):
    if os.path.exists(TOKEN_FILE_PATH):
        LOGGER.debug("Found token file. Using cached tokens.")
        with open(TOKEN_FILE_PATH, 'r') as f:
            tokens = f.readlines()
            refresh_token = tokens[0].strip().split('=')[1]
            access_token = tokens[1].strip().split('=')[1]
        bb = BirdBuddy(args.username, args.password, refresh_token, access_token)
    else:
        LOGGER.debug("No token file found.")
        bb = BirdBuddy(args.username, args.password)
    return bb

def save_tokens(bb):
    with open(TOKEN_FILE_PATH, 'w') as f:
        f.write(f"refresh_token={bb._refresh_token}\n")
        f.write(f"access_token={bb._access_token}\n")

def set_cooldown():
    with open(COOLDOWN_FILE_PATH, 'w') as f:
        f.write(str(int(time.time()) + 10 * 60))
    LOGGER.info("Set cooldown.")

def is_in_cooldown():
    if os.path.exists(COOLDOWN_FILE_PATH):
        with open(COOLDOWN_FILE_PATH, 'r') as f:
            cooldown_time = int(f.read().strip())
            if time.time() < cooldown_time:
                return True

    return False

def clear_cooldown():
    if os.path.exists(COOLDOWN_FILE_PATH):
        os.remove(COOLDOWN_FILE_PATH)
        LOGGER.debug("Cleared cooldown.")

def set_recovery():
    with open(RECOVERY_FILE_PATH, 'w') as f:
        f.write('')

def clear_recovery():
    if os.path.exists(RECOVERY_FILE_PATH):
        os.remove(RECOVERY_FILE_PATH)

def is_sleepy_time(city):
    s = sun(city.observer, tzinfo=city.timezone)
    sunset = s['sunset']
    now = datetime.now(sunset.tzinfo)
    LOGGER.debug("It is currently %s. Calculated sun information: %s", now, s)
    return now > sunset + timedelta(minutes=10)   

def get_feeder_by_name(bb, name):
    for feeder_id, feeder in bb.feeders.items():
        if feeder.name == name:
            LOGGER.info("Found feeder: %s (ID: %s): %s", feeder.name, feeder_id, feeder)
            return feeder

    return None

def run_restream_ffmpeg(in_url, out_url, output_codec, log_level="WARNING"):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info" if log_level == "DEBUG" else "error",
        "-i", in_url,
        "-c:v", output_codec,
        "-c:a", "copy",
        "-f", "rtsp",
        out_url
    ]

    return run_ffmpeg(command)

def run_splash_ffmpeg(out_url, output_codec, log_level="WARNING"):
    command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "info" if log_level == "DEBUG" else "error",
            "-re",
            "-stream_loop", "-1",
            "-i", "bb-streamer-splash.mp4",
            "-c:v", "copy",
            "-s", "1536x2048",
            "-f", "rtsp",
            out_url
        ]

    return run_ffmpeg(command)

def run_ffmpeg(command):
    process = None
    try:
        LOGGER.debug("ffmpeg command: %s", command)
        process = subprocess.Popen(
            command,
            stdout=sys.stdout,
            stderr=sys.stderr,
            preexec_fn=os.setsid)
        LOGGER.debug("ffmpeg process started: %s", process.pid)
    except FileNotFoundError:
        LOGGER.error("ffmpeg not found. Make sure it's installed and in your PATH.")
    except Exception as e:
        LOGGER.error("Error starting ffmpeg: %s", e)

    return process

def stop_ffmpeg(ffmpeg_process, name):
    if ffmpeg_process is not None and ffmpeg_process.poll() is None:
        LOGGER.info("%s ffmpeg process is running. Terminating...", name)
        ffmpeg_process.terminate()
        time.sleep(2)
        if ffmpeg_process.poll() is None:
            LOGGER.warning("%s ffmpeg process still running. Killing...", name)
            os.killpg(os.getpgid(ffmpeg_process.pid), signal.SIGKILL)

        LOGGER.info("Stopped %s ffmpeg process.", name)
        LOGGER.debug("%s ffmpeg process return code: %s", name, ffmpeg_process.returncode)

def signal_handler(sig, frame):
    global terminate
    terminate = True

if __name__ == "__main__":
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root.addHandler(handler)

    LOGGER = logging.getLogger(__package__)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)
    main()