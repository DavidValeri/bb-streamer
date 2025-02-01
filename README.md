Create minimal go2rtc.yaml file defining your Birdbuddy feeder streams.

Note that this project relies on [pybirdbuddy](https://github.com/jhansche/pybirdbuddy) and therefore only Birdbuddy accounts using a username and password will work. If you created your account using a social sign-in option, you will need to create a new account and move your feeders.
```
streams:
  birdbuddy: exec:/app/start-and-refresh-stream.py --username <EMAIL> --password <PASSWORD> --feeder_name "<FEEDER_NAME>" --out_url {output}#killsignal=15
```

Launch the container, forwarding ports or using host networking for the supported go2rtc protocols that you want to restream over.
```
docker run -v ./:/config -p 8554:8554 --name bb-streamer ghcr.io/davidvaleri/bb-streamer:main
```