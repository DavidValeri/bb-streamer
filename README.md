Note that this project relies on [pybirdbuddy](https://github.com/jhansche/pybirdbuddy) and therefore only Bird Buddy accounts using a username and password will work. If you created your account using a social sign-in option, you will need to create a new account and move your feeders.

# Publisher
You can run the bb-stream-publisher image to push the stream to an endpoint, such as a go2rtc instance or a Frigate instance. The stream is started / restarted while the container is running, stopping only when the feeder is asleep or the battery is too low. See start-and-refresh-stream.py's configuration options to fine tune the allowed battery level ranges.

This approach is preferred for usage with projects such as Frigate as it removes the complexity of multiple layers of timeouts and error handling. For example, Frigate has hardcoded timeouts on detect / record processes and configurable timeouts on its own ffmpeg child processes, and optional go2rtc when in use.

Launch the container.
```
docker run -v ./:/config --name bb-streamer - ghcr.io/davidvaleri/bb-streamer-publisher:main --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --out_url <RTSP_TARGET>
```


# Server
You can run the bb-streamer-server image to make the stream available via go2rtc. The stream is initialized on demand when there is one or more active consumers connected to the go2rtc server. It should be noted that the initialization of the stream can take some time and therefore client timeouts should be fairly generous, on the order of 45 seconds or more, in order to avoid the client disconnecting and go2rtc terminating the stream while it is still being initialized. The stream will not start when the feeder is aspleep or the battery is too low. See start-and-refresh-stream.py's configuration options to fine tune the allowed battery level ranges.

Create minimal go2rtc.yaml file defining your Birdbuddy feeder stream(s).
```
streams:
  Bird_Buddy: exec:/app/start-and-refresh-stream.py --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --out_url {output}#killsignal=15#killtimeout=15
```

Launch the container, forwarding ports or using host networking for the supported go2rtc protocols that you want to restream over.
```
docker run -v ./:/config -p 8554:8554 --name bb-streamer ghcr.io/davidvaleri/bb-streamer-server:main
```

In this example, the Bird Buddy stream will be accessible at `rtsp://localhost:8554/Bird_Buddy`. See the go2rtc documentation for all available protocols, transcoding options, and more.