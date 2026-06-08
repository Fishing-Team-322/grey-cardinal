#!/bin/sh
set -eu

mkdir -p /tmp/pulse /tmp/telemost-recordings
pulseaudio --daemonize=yes --exit-idle-time=-1 \
  --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" \
  --load="module-null-sink sink_name=telemost_sink sink_properties=device.description=Telemost"
pactl set-default-sink telemost_sink
pactl set-default-source telemost_sink.monitor

export DISPLAY=:99
Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
sleep 1

exec python -m telemost_recorder.main
