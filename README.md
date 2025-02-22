![bb-streamer-logo-wide](https://github.com/user-attachments/assets/32319903-7e16-442a-b8a2-37cf38c239c7)
BB Streamer enables you to stream live video from Bird Buddy smart bird feeders to the viewer or recorder of your choice. Configuration options allow you to control the minimum battery charge for streaming to start and the minimum battery charge for active streaming to stop. Due to quirks in the Bird Buddy firmware / and or API implementation, streaming must be stopped before the device attempts to enter "deep sleep" each night or the Bird Buddy becomes non-responsive and the API returns unusual results until the Bird Buddy is restarted. To avoid this situation, configurations options for your location (latitude and longitude) and timezone are necessary to allow for streaming to terminate before the Bird Buddy attempts to enter deep sleep.

Note that this project relies on [pybirdbuddy](https://github.com/jhansche/pybirdbuddy) and therefore only Bird Buddy accounts using a username and password will work. If you created your account using a social sign-in option, you will need to create a new account and move your feeders to this new account. You can share your feeders with your original account if you do not want to abandon your previously collected postcards.

BB Streamer is available as a Docker container for linux/amd64 and linux/arm64 architectures. You can run BB Streamer in two modes. As a server for the video that you can connect to from a viewer or a video processing tool such as ffmpeg and as a publisher sending the stream to a target RTSP URL. These two deployment options are documented below.

This project was built to stream Bird Buddy feeds into Frigate for object detection and further experimentation with LLMs and bird specific models for species detection. Using Frigate also opens the door to Home Assistant integrations and dashboards about the feathered freeloaders at your feeder.

# Deployment Options

Both options expect a volume attached at `/config`. BB Streamer uses this folder to store state information such as cached API tokens and information about recovery and cooldown states. You can delete any file in this folder without concern. BB Streamer will recreate the files as it runs.

## Publisher
You can run the bb-stream-publisher image to push the stream to an endpoint, such as go2rtc or Frigate. The stream is started / restarted while the container is running, stopping only when the feeder is asleep or the battery is too low. See the configuration options below to fine tune the container's behavior.

This approach is preferred for usage with projects such as Frigate as it removes the complexity of multiple layers of timeouts working against each other. For example, Frigate has hardcoded timeouts on detect / record processes, configurable timeouts on its own ffmpeg child processes, and configurable timeouts on go2rtc when in use. A Bird Buddy stream rarely initializes in less than the hardcoded timeouts on Frigate's detect / record processes and you end up in a cycle of disconnects and retries as a result. This approach avoids these timeouts and makes you life easier.

Launch the container.
```
docker run -v ./:/config --name bb-streamer -d --restart unless-stopped ghcr.io/davidvaleri/bb-streamer-publisher:latest --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --out_url <RTSP_TARGET> --continuous true --latitude <LATITUDE> --longitude <LONGITUDE> --timezone <TIME_ZONE_NAME>
```

# Configuration Options

* username - REQUIRED - Your Bird Buddy username
* password - REQUIRED - Your Bird Buddy password
* feeder_name - REQUIRED - The friendly name of your feeder as it appears in the Bird Buddy app
* out_url - REQUIRED - The RTSP URL to publish the stream to
* continuous - OPTIONAL - Defaults to false. If false, the process will run once to completion and stop. You container configuration in Docker will handle the restart behavior at that point. Set to true to allow the BB Streamer to handle retries and error handling internally. In this deployment model, it is recommended to set the vaue to true.
* latitude - REQUIRED - The latitude of the camera location as a decimal number of degrees. For example -0.1403923937279329.
* longitude - REQUIRED - The longitude of the camera location as a decimal number of degrees. For example -90.40930143839682.
* timezone - REQUIRED - The timezone of the camera location as a string. For example America/New_York. You can find a human readable list to choose from on Wikipedia's [List of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
* min_starting_battery_level - OPTIONAL - Recovery state begins when the battery level drops below min_battery_level. Once in the recovery state, streaming will not resume until the battery level is above min_starting_battery_level. Defaults to 70%.
* min_battery_level - OPTIONAL - The battery level below which recovery state begins. See min_starting_battery_level. Defaults to 40%

## Server
You can run the bb-streamer-server image to make the stream available via go2rtc. The stream is initialized on demand when there is one or more active consumers connected to the go2rtc server. It should be noted that the initialization of the stream can take some time and therefore client timeouts should be fairly generous, on the order of 45 seconds or more, in order to avoid the client disconnecting and go2rtc terminating the stream while it is still being initialized. The stream will not start when the feeder is aspleep or the battery is too low. See start-and-refresh-stream.py's configuration options to fine tune the allowed battery level ranges.

Create minimal go2rtc.yaml file defining your Bird Buddy feeder stream(s).
```
streams:
  Bird_Buddy: exec:/app/start-and-refresh-stream.py --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --out_url {output} --latitude <LATITUDE> --longitude <LONGITUDE> --timezone <TIME_ZONE_NAME>#killsignal=15#killtimeout=15
```

Launch the container, forwarding ports or using host networking for the supported go2rtc protocols that you want to restream over.
```
docker run -v ./:/config -p 8554:8554 --name bb-streamer -d --restart unless-stopped ghcr.io/davidvaleri/bb-streamer-server:latest
```

In this example, the Bird Buddy stream will be accessible at `rtsp://localhost:8554/Bird_Buddy`. See the go2rtc documentation for all available protocols, transcoding options, and more.

# Configuration Options
* username - REQUIRED - Your Bird Buddy username
* password - REQUIRED - Your Bird Buddy password
* feeder_name - REQUIRED - The friendly name of your feeder as it appears in the Bird Buddy app
* out_url - REQUIRED - The RTSP URL to publish the stream to
* latitude - REQUIRED - The latitude of the camera location as a decimal number of degrees. For example -0.1403923937279329.
* longitude - REQUIRED - The longitude of the camera location as a decimal number of degrees. For example -90.40930143839682.
* timezone - REQUIRED - The timezone of the camera location as a string. For example America/New_York. You can find a human readable list to choose from on Wikipedia's [List of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
* min_starting_battery_level - OPTIONAL - Recovery state begins when the battery level drops below min_battery_level. Once in the recovery state, streaming will not resume until the battery level is above min_starting_battery_level. Defaults to 70%.
* min_battery_level - OPTIONAL - The battery level below which recovery state begins. See min_starting_battery_level. Defaults to 40%

# Using BB Streamer Publisher with Frigate

BB Streamer can be used with Frigate's object detection capabilities to capture recordings and snapshots of visitors to your Bird Buddy feeders. Birds are fast moving things so the setup below increases the detection frame rate to improve the chances of detecting visitors. BB Streamer has not been tested with the base (free) Frigate model. The Frigate Plus model has moderate success out of the box; however, adding your own images of birds at your feeder dramatically increases detection rates. You may want to lower the confidence thresholds for bird objects to start and increase it again after training a Frigate+ model with your own labeled images. Since you may end up with thousands of tracked bird objects in a matter of days, you may want to disable generative AI on detections from your Bird Buddy cameras if you have them enabled in your setup. The built-in generative AI features in Frigate, although not able to set sub-labels, combined with a custom prompt for bird objects, does open the door to some interesting possibilities to generate human readable or structured machine readable data on the species, sex, etc. in the description of detected birds.

Add empty streams to the go2rtc section for your Bird Buddy feeders.

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

If you want to play around with generative AI general purpose models, here is an example configuration that has been used with Google's gemini-2.0-flash model. Replace `<CITY>` and `<STATE>` with your location.

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
      help identify the bird and rule out unlikely birds. 

      Your response should be a JSON object and only a JSON object. No text should 
      appear in the response other than the JSON object itself. The object attributes 
      are described below.

      commonName - The bird's complete common name in title case.

      confidence - A percentage, 0 to 1, representing the confidence of the bird 
      identification. Do not use any text in the image to determine this value.

      scientificName - The scientific name of the bird identification.

      sex - If the identified bird species is sexually dimorphic, identify the 
      likely sex. Use "male" or "female" as the values. If the sex cannot be determined, 
      use "unknown".

      age - The category best matching the bird's age. Use "juvenile", "immature", "adult",
      or "unkown".

      quality - An object describing the quality of the image based on the attribute 
      definitions below. Give all scores as a numeric value from 0 to 1.

      framing - Is the bird fully in the frame? 0 means none of the bird is visible and 1 means
      the entire bird is visible.

      focus - Is the bird in sharp focus with no signs of motion blur? 0 means the entire bird
      is blury and 1 means the entire bird is in sharp focus.

      exposure - Is the exposure of the bird good? Lower scores indicate that the bird is in
      shadow, silhouette, or is overexposed and details of the bird are lost in the picture.

      composite - The value is based on the following formula
      (isInFrame * 0.3 + isInFocus * 0.5 + isWellLit * 0.2).
  objects:
    - bird
```
