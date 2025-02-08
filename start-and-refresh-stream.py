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

terminate = False
RECOVERY_FILE_PATH = "/config/recovery"
TOKEN_FILE_PATH = "/config/tokens"
COOLOFF_FILE_PATH = "/config/cooloff"

def main():
    global root
    global terminate

    parser = argparse.ArgumentParser(description="Description of your program")
    parser.add_argument('--username', type=str, required=True, help='BirdBuddy username')
    parser.add_argument('--password', type=str, required=True, help='BirdBuddy password')
    parser.add_argument('--feeder_name', type=str, required=True, help='Feeder name')
    parser.add_argument('--out_url', type=str, required=True, help='Output URL for ffmpeg')
    parser.add_argument('--log_level', type=str, default='INFO', help='Log level')
    parser.add_argument('--min_starting_battery_level', type=int, default=70, help='Minimum battery level to start streaming after entering recovery state')
    parser.add_argument('--min_battery_level', type=int, default=40, help='Battery level at which the stream is stopped and recovery state is entered')
    parser.add_argument('--output_codec', type=str, default='copy', help='ffmpeg codec for output transcoding')

    args = parser.parse_args()

    root.setLevel(args.log_level)

    if os.path.exists(COOLOFF_FILE_PATH):
        with open(COOLOFF_FILE_PATH, 'r') as f:
            cooldown_timestamp = int(f.read().strip())
        if time.time() < cooldown_timestamp:
            LOGGER.error("Cooloff period active. Exiting.")
            return 1
        else:
            os.remove(COOLOFF_FILE_PATH)

    bb = init_bb(args)

    try:
        asyncio.run(bb.refresh())
        save_tokens(bb)
    except Exception as e:
        LOGGER.error("Error refreshing Birdbuddy: %s", e)
        return 2

    feeder = get_feeder_by_name(bb, args.feeder_name)
    if not feeder:
        LOGGER.error("Feeder with name '%s' not found.", args.feeder_name)
        return 3
    
    if feeder.state != FeederState.READY_TO_STREAM and feeder.state != FeederState.STREAMING:
        if feeder.state in [FeederState.DEEP_SLEEP, FeederState.OFFLINE, FeederState.OFF_GRID, FeederState.OUT_OF_FEEDER]:
            set_cooloff()

        LOGGER.error("Feeder is not streaming or ready to stream.")
        return 4

    if os.path.exists(COOLOFF_FILE_PATH):
        os.remove(COOLOFF_FILE_PATH)

    if feeder.battery.percentage < args.min_battery_level:
        LOGGER.error("Battery level, %s, is less than %s. Entering recovery state.", feeder.battery.percentage, args.min_battery_level)
        with open(RECOVERY_FILE_PATH, 'w') as f:
            f.write('')
        set_cooloff()
        return 5

    if os.path.exists(RECOVERY_FILE_PATH):
        if feeder.battery.percentage < args.min_starting_battery_level:
            LOGGER.error("Battery level, %s, is less than %s. Not starting stream due to recovery state.", feeder.battery.percentage, args.min_starting_battery_level)
            return 6

    if os.path.exists(RECOVERY_FILE_PATH):
        os.remove(RECOVERY_FILE_PATH)

    result = asyncio.run(bb.watching_start(feeder.id))
    LOGGER.info("Birdbuddy stream started.")

    if terminate:
        LOGGER.info("Received termination signal. Exiting...")
        return 0

    in_url = result["watching"]["streamUrl"]
    if in_url is None:
        LOGGER.error("Stream URL was None.")
        set_cooloff()
        return 7

    ffmpeg_process = run_ffmpeg(
        in_url,
        args.out_url,
        args.output_codec,
        "info" if args.log_level == "DEBUG" else "warning")

    if ffmpeg_process is None:
        return 8

    LOGGER.info("ffmpeg started.")

    while not terminate and ffmpeg_process.poll() is None:
        # Refresh stream every 10 seconds for one minute before rechecking battery level.
        i = 0
        while i < 6 and not terminate:
            if terminate:
                break
            time.sleep(10)
            try:
                asyncio.run(bb.watching_active_keep())
                LOGGER.info("Refreshed stream.")
            except Exception as e:
                LOGGER.warning("Error refreshing stream: %s", e)
            i += 1

        try:
            asyncio.run(bb.refresh())
            save_tokens(bb)
        except Exception as e:
            LOGGER.warning("Error refreshing Birdbuddy: %s", e)

        if feeder.battery.percentage < args.min_battery_level:
            LOGGER.error("Battery level, %s, is less than %s. Entering recovery state.", feeder.battery.percentage, args.min_battery_level)
            with open(RECOVERY_FILE_PATH, 'w') as f:
                f.write('')
            terminate = True

    if terminate:
        LOGGER.info("Stopping ffmpeg...")
        if ffmpeg_process.poll() is None:
            LOGGER.info("ffmpeg process still running. Terminating...")
            ffmpeg_process.terminate()
            time.sleep(5)
            if ffmpeg_process.poll() is None:
                LOGGER.info("ffmpeg process still running. Killing...")
                os.killpg(os.getpgid(ffmpeg_process.pid), signal.SIGKILL)
                time.sleep(5)

    LOGGER.debug("ffmpeg process return code: %s", ffmpeg_process.returncode)
    LOGGER.info("Done.")

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

def set_cooloff():
    with open(COOLOFF_FILE_PATH, 'w') as f:
        f.write(str(int(time.time()) + 10 * 60))
    LOGGER.info("Set cooloff.")

def get_feeder_by_name(bb, name):
    for feeder_id, feeder in bb.feeders.items():
        if feeder.name == name:
            LOGGER.info("Found feeder: %s (ID: %s): %s", feeder.name, feeder_id, feeder)
            return feeder

    return None

def run_ffmpeg(in_url, out_url, output_codec, log_level="warning"):
    try:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", log_level.lower(),
            "-i", in_url,
            "-c:v", output_codec,
            "-c:a", "copy",
            "-f", "rtsp", out_url
        ]
        process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr, preexec_fn=os.setsid)
        return process
    except FileNotFoundError:
        LOGGER.error("Error: ffmpeg not found. Make sure it's installed and in your PATH.")
        return None

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