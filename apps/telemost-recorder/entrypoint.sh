#!/bin/sh
set -eu

export HOME=/root
export XDG_RUNTIME_DIR=/tmp/pulse-runtime
mkdir -p /tmp/pulse /tmp/telemost-recordings "$XDG_RUNTIME_DIR" /data/profile /data/screenshots
chmod 700 "$XDG_RUNTIME_DIR"

# Kill any stale daemon from a previous container run, then start a fresh one.
pulseaudio --kill 2>/dev/null || true
rm -f /tmp/pulse/native 2>/dev/null || true

start_pulse() {
  pulseaudio --daemonize=yes --exit-idle-time=-1 --disallow-exit \
    --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" \
    --load="module-null-sink sink_name=telemost_sink sink_properties=device.description=Telemost"
}

# pulseaudio prints a harmless "not intended to run as root" warning; only the
# exit status matters. Retry once because a lingering daemon can lose the race.
start_pulse || { sleep 2; pulseaudio --kill 2>/dev/null || true; start_pulse; }

# Wait until the daemon answers before configuring sinks.
i=0
until pactl info >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 20 ]; then
    echo "pulseaudio did not become ready" >&2
    break
  fi
  sleep 0.5
done

pactl set-default-sink telemost_sink || true
pactl set-default-source telemost_sink.monitor || true
echo "pulseaudio ready: $(pactl info 2>/dev/null | grep -i 'Server Name' || echo unknown)"

# Start our own Xvfb and wait until its X socket actually exists before launching
# the browser. xvfb-run is avoided on purpose: as PID 1 its SIGUSR1 readiness
# handshake hangs, and a fixed `sleep` races the server. Polling the socket is
# deterministic and fixes the intermittent "Missing X server" join failures.
export DISPLAY=:99
rm -f /tmp/.X99-lock 2>/dev/null || true
Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!

i=0
until [ -S /tmp/.X11-unix/X99 ]; do
  i=$((i + 1))
  if ! kill -0 "$XVFB_PID" 2>/dev/null; then
    echo "Xvfb exited during startup:" >&2
    cat /tmp/xvfb.log >&2 || true
    exit 1
  fi
  if [ "$i" -ge 40 ]; then
    echo "Xvfb did not create its socket in time" >&2
    exit 1
  fi
  sleep 0.25
done
echo "Xvfb ready on $DISPLAY"

exec python -m telemost_recorder.main
