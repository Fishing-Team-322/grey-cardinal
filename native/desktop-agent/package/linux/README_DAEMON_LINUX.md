# Grey Cardinal Daemon for Linux Debian/Ubuntu

Status: preview packaging skeleton.

The repository includes the target package layout for a future
`grey-cardinal-daemon-linux-amd64.deb`, but the current native audio capture
implementation is Windows WASAPI-only. Linux PipeWire/PulseAudio capture still
needs an implementation before this package should be published as available.

## Target Install Flow

```bash
sudo dpkg -i grey-cardinal-daemon-linux-amd64.deb
sudo apt-get install -f
sudo nano /etc/grey-cardinal-daemon/config.toml
sudo systemctl enable --now grey-cardinal-daemon
journalctl -u grey-cardinal-daemon -f
```

## Smoke Upload Preview

```bash
BACKEND_URL="https://fishingteam.su" ./smoke_upload_test.sh
```

This verifies backend ingest only. It does not prove real microphone or system
audio capture on Linux.
