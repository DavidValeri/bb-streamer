![bb-streamer-logo-wide](https://github.com/user-attachments/assets/f422e7e4-644e-4b6c-bba4-37e7a4463481)
BB Streamer enables you to stream live video from Bird Buddy smart bird feeders to the viewer or recorder of your choice. Configuration options allow you to control the minimum battery charge for streaming to start and the minimum battery charge for active streaming to stop. Due to quirks in the Bird Buddy firmware / and or API implementation, streaming must be stopped before the device attempts to enter "deep sleep" each night or the Bird Buddy becomes non-responsive and the API returns unusual results until the Bird Buddy is restarted. To avoid this situation, configurations options for your location (latitude and longitude) and timezone are necessary to allow for streaming to terminate before the Bird Buddy attempts to enter deep sleep.

Note that this project relies on [pybirdbuddy](https://github.com/jhansche/pybirdbuddy) and therefore only Bird Buddy accounts using a username and password will work. If you created your account using a social sign-in option, you will need to create a new account and move your feeders to this new account. You can share your feeders with your original account if you do not want to abandon your previously collected postcards.

BB Streamer is available as a Docker container for linux/amd64 and linux/arm64 architectures. You can run BB Streamer in two modes. As a server for the video that you can connect to from a viewer or a video processing tool such as ffmpeg and as a publisher sending the stream to a target RTSP URL. These two deployment options are documented below.

This project was built to stream Bird Buddy feeds into Frigate for object detection and further experimentation with LLMs and bird specific models for species detection. Using Frigate also opens the door to Home Assistant integrations and dashboards about the feathered freeloaders at your feeder.

# Deployment Options

Both options expect a volume attached at `/config`. BB Streamer uses this folder to store state information such as cached API tokens and information about recovery and cooldown states. You can delete any file in this folder without concern. BB Streamer will recreate the files as it runs.

## Publisher

This approach is preferred when you don't intend to perform any transcoding in BB Streamer itself, you have another system listening for incoming streams, and/or you want the minimal footprint possible for BB Streamer.

You can run the bb-stream-publisher image to push the stream to an external endpoint, such as a go2rtc instance or Frigate. The Bird Buddy stream is started / restarted while the container is running, stopping only when the feeder is asleep or the battery is too low. If run in `continuous` mode, the default, a splash screen is streamed when the Bird Buddy stream is not active.

See the configuration options below to fine tune the BB Streamer's behavior.

Launch the container.
```
docker run -v ./:/config --name bb-streamer -d --restart unless-stopped ghcr.io/davidvaleri/bb-streamer-publisher:latest --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --out_url <RTSP_TARGET> --latitude <LATITUDE> --longitude <LONGITUDE> --timezone <TIME_ZONE_NAME>
```

### Configuration Options

* username - REQUIRED - Your Bird Buddy username
* password - REQUIRED - Your Bird Buddy password
* feeder_name - REQUIRED - The friendly name of your feeder as it appears in the Bird Buddy app
* out_url - REQUIRED - The RTSP URL to publish the stream to
* continuous - OPTIONAL - Defaults to true. If false, the process will run once to completion and stop. The container configuration in Docker will handle the restart behavior at that point. Set to true to allow the BB Streamer to handle retries and error handling internally while streaming a splash screen when the Bird Buddy stream is not active.
* latitude - REQUIRED - The latitude of the camera location as a decimal number of degrees. For example -0.1403923937279329.
* longitude - REQUIRED - The longitude of the camera location as a decimal number of degrees. For example -90.40930143839682.
* timezone - REQUIRED - The timezone of the camera location as a string. For example America/New_York. You can find a human readable list to choose from on Wikipedia's [List of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
* min_starting_battery_level - OPTIONAL - Recovery state begins when the battery level drops below min_battery_level. Once in the recovery state, streaming will not resume until the battery level is above min_starting_battery_level. Defaults to 70%.
* min_battery_level - OPTIONAL - The battery level below which recovery state begins. See min_starting_battery_level. Defaults to 40%

## Server
This approach is preferred when you intend to perform transcoding in BB Streamer via go2rtc, you want to view the stream in a client such as VLC, or you have other complex needs that can be handled via configuration in go2rtc.

You can run the bb-streamer-server image to make the stream available via WebRTC, RTSP, and other protocols via go2rtc. The Bird Buddy stream is started / restarted on demand when there is one or more active consumers connected to the go2rtc server.

Note that the initialization of the stream can take some time and client timeouts should be fairly generous, on the order of 45 seconds or more, in order to avoid the client disconnecting and go2rtc terminating the stream while it is still being initialized.

See the configuration options below to fine tune the BB Streamer's behavior.

Create minimal go2rtc.yaml file defining your Bird Buddy feeder stream(s).
```
streams:
  Bird_Buddy: exec:/app/start-and-refresh-stream.py --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --continuous false --out_url {output} --latitude <LATITUDE> --longitude <LONGITUDE> --timezone <TIME_ZONE_NAME>#killsignal=15#killtimeout=15
```

Launch the container, forwarding ports or using host networking for the supported go2rtc protocols that you want to restream over.
```
docker run -v ./:/config -p 8554:8554 --name bb-streamer-4 -d --restart unless-stopped ghcr.io/davidvaleri/bb-streamer-server:latest
```

In this example, the Bird Buddy stream will be accessible at `rtsp://localhost:8554/Bird_Buddy`. See the go2rtc documentation for all available protocols, transcoding options, and more.

### Configuration Options
* username - REQUIRED - Your Bird Buddy username
* password - REQUIRED - Your Bird Buddy password
* feeder_name - REQUIRED - The friendly name of your feeder as it appears in the Bird Buddy app
* out_url - REQUIRED - The RTSP URL to publish the stream to. In this deployment model, use the {output} token so go2rtc can provide the dynamic target URL.
* continuous - REQUIRED - Must be false in this mode of usage.
* latitude - REQUIRED - The latitude of the camera location as a decimal number of degrees. For example -0.1403923937279329.
* longitude - REQUIRED - The longitude of the camera location as a decimal number of degrees. For example -90.40930143839682.
* timezone - REQUIRED - The timezone of the camera location as a string. For example America/New_York. You can find a human readable list to choose from on Wikipedia's [List of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
* min_starting_battery_level - OPTIONAL - Recovery state begins when the battery level drops below min_battery_level. Once in the recovery state, streaming will not resume until the battery level is above min_starting_battery_level. Defaults to 70%.
* min_battery_level - OPTIONAL - The battery level below which recovery state begins. See min_starting_battery_level. Defaults to 40%

# Using BB Streamer Publisher with Frigate

BB Streamer can be used with Frigate's object detection capabilities to capture recordings and snapshots of visitors to your Bird Buddy feeders. Birds are fast moving things so the setup below increases the detection frame rate to improve the chances of detecting visitors. BB Streamer has not been tested with the base (free) Frigate model. The Frigate Plus model has moderate success out of the box; however, adding your own images of birds at your feeder dramatically increases detection rates. You may want to lower the confidence thresholds for bird objects to start and increase it again after training a Frigate+ model with your own labeled images. Since you may end up with thousands of tracked bird objects in a matter of days, you may want to disable generative AI on detections from your Bird Buddy cameras if you have them enabled in your setup. The built-in generative AI features in Frigate, although not able to set sub-labels, combined with a custom prompt for bird objects, does open the door to some interesting possibilities to generate human readable or structured machine readable data on the species, sex, etc. in the description of detected birds.

Add empty streams to the go2rtc section for your Bird Buddy feeders. Note that if you have more than one stream, you will need to put each Bird Buddy into its own account to avoid issues with Bird Budy's restrictions and the way BB Streamer works.

```
go2rtc:
  # log:
  #   level: debug
  rtsp:
    username: <RTSP_USER>
    password: <RTSP_PASS>
  streams:

    Bird_Buddy_1:

    Bird_Buddy_2:

    ...

    Bird_Buddy_n:
```

Add a camera entry for each of your Bird Buddy feeders.

```
cameras:
  Bird_Buddy_1:
    enabled: true
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/Bird_Buddy_1
          input_args: preset-rtsp-restream
          roles:
            - record
            - detect
      output_args:
        record: preset-record-generic
    audio:
      enabled: false
    detect:
      enabled: true
      fps: 10
      min_initialized: 2
      width: 1536
      height: 2048
    objects:
      track:
        - bird
        - squirrel
    <YOUR_OPTIONAL_RECORD_AND_REVIEW_SETTINGS>
    genai:
      enabled: false
```

Configure BB Streamer Publisher to publish the stream to Frigate's go2rtc instance using a URL such as `rtsp://<RTSP_USER>:<RTSP_PASS>@<FRIGATE_HOST>:8554/Bird_Buddy_4`. You can use the IP or domain name for your host if you run Frigate and BB Streamer on different hosts or you can use the Frigate container name if you are running BB Streamer and Frigate containers on the same host.

If you want to play around with generative AI general purpose models, here is an example configuration that has been used with Google's gemini-2.0-flash model. Replace `<CITY>` and `<STATE>` with your location. This example by no means replaces a specialized species classification model, but it does demonstrate some ideas such as using AI to help cull out lower quality pictures and attempting to capture age and sex information.

```
genai:
  enabled: true
  use_snapshot: true
  prompt: "Analyze the {label} in this image or these images. Do not analyze the background."
  object_prompts:
    bird: > 
      Observe the bird to identify the bird species and information about it like sex and age.

      If there is more than one bird in the picture, focus on the most prominent bird
      in the image or the bird with a box drawn around it. The picture was taken today
      in <CITY>, <STATE> at a bird feeder. Use this time, location, and behavior data to
      help identify the bird and rule out unlikely birds. When judging the quality of the
      photo, you are a hard critic.

      Your response should be a JSON object and only a JSON object. No text should
      appear in the response other than the JSON object itself. The object attributes
      are described below.

      commonName - The bird's complete common name in title case. If unknown, set to null.

      scientificName - The scientific name of the bird identification. If unknown, set
      to null.

      confidence - A percentage, 0 to 1, representing the confidence of the bird species
      identification. Do not use any text in the image to determine this value. If the
      species is unknown, set to 0.

      sex - If the identified bird species is sexually dimorphic, identify the
      likely sex. Use "MALE" or "FEMALE" as the values. If the sex cannot be determined,
      use "UNKNOWN".

      age - The category best matching the bird's age. Use "JUVENILE", "IMMATURE", "ADULT",
      or "UNKNOWN".

      quality - An object describing the quality of the image based on the attribute
      definitions below. Give all scores as a numeric value from 0 to 1.

      framing - Is the bird fully in the frame? 0 means none of the bird is visible and 1 means
      the entire bird is visible.

      focus - Is the bird in sharp focus with no signs of motion blur? 0 means the entire bird
      is blurry and 1 means the entire bird is in sharp focus.

      exposure - Judge the exposure of the bird and only the bird. 0 means that the bird
      is in shadow, silhouette, or is overexposed. 1 means that the bird is well exposed and
      details are clearly visible.

      sayCheese - A measure of how much of the bird's head and beak are visible in the frame.
      0 means that none of the bird's head and beak are in the frame or you can only see the 
      back or top of the bird's head. 1 means the bird's entire head and beak are the frame and
      that the view of these features is a profile view, looking straight on at the camera, or
      something between these two extremes.

      composite - The value is based on the following formula
      (framing * 0.1 + sayCheese * 0.4 + focus * 0.3 + exposure * 0.2).
  objects:
    - bird
```
