# Generate h265 video for splash screen

From this folder run the following command.

```
ffmpeg -loop 1 -f image2 -i ./bb-streamer-splash.jpg -r 1 -c:v libx265 -crf 0 -preset veryslow -s 1536x2048 -t 5 ./bb-streamer-splash.mp4
```

NOTE: H265 encoding did not function correctly when using the ffmpeg Docker image on macOS w/ Apple silicon. It did function correctly using the native build of ffmpeg for macOS.