# Cross-platform Daemon Installer Setup

Grey Cardinal serves daemon release metadata from:

```text
apps/frontend-dashboard/public/downloads/daemon-manifest.json
```

The production page reads this manifest and renders the existing Daemon setup
flow as a platform selector for Windows, macOS, and Linux.

## Production URLs

- Windows MSI: `https://fishingteam.su/downloads/grey-cardinal-daemon-windows-x64.msi`
- Linux DEB target: `https://fishingteam.su/downloads/grey-cardinal-daemon-linux-amd64.deb`
- macOS DMG target: `https://fishingteam.su/downloads/grey-cardinal-daemon-macos-universal.dmg`

Only artifacts with `status: "available"` are active download buttons in the UI.
Preview artifacts are shown with disabled buttons to avoid 404 flows.

## Windows MSI

Current status: available.

- Artifact: `grey-cardinal-daemon-windows-x64.msi`
- Version: `0.3.0`
- Size: `104 KB`
- SHA256: `B24AA357A349488405133B6CBF4B428FA2FD6D70B45895B98BCDA3296774F241`
- Install directory: `C:\Program Files\Grey Cardinal Daemon\`
- Config/logs: `%LOCALAPPDATA%\GreyCardinal\Daemon\`

Build locally:

```powershell
.\scripts\package_windows_msi.ps1 -Configuration Release -Version 0.3.0
```

Install:

```powershell
msiexec /i .\grey-cardinal-daemon-windows-x64.msi
```

Smoke upload:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Grey Cardinal Daemon\smoke_upload_test.ps1" -BackendUrl "https://fishingteam.su"
```

Open logs:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Grey Cardinal Daemon\open_logs.ps1"
```

Uninstall:

```powershell
msiexec /x .\grey-cardinal-daemon-windows-x64.msi
```

## Linux Debian/Ubuntu

Current status: preview.

Target flow:

```bash
sudo dpkg -i grey-cardinal-daemon-linux-amd64.deb
sudo apt-get install -f
sudo nano /etc/grey-cardinal-daemon/config.toml
sudo systemctl enable --now grey-cardinal-daemon
journalctl -u grey-cardinal-daemon -f
```

Preview files:

- `native/desktop-agent/package/linux/config.example.toml`
- `native/desktop-agent/package/linux/grey-cardinal-daemon.service`
- `native/desktop-agent/package/linux/smoke_upload_test.sh`
- `native/desktop-agent/package/linux/README_DAEMON_LINUX.md`
- `scripts/package_linux_deb.sh`

Linux PipeWire/PulseAudio capture is not implemented yet, so the DEB artifact is
not published as an active download.

## macOS

Current status: preview.

Target flow:

```bash
open grey-cardinal-daemon-macos-universal.dmg
tail -f ~/Library/Logs/GreyCardinal/Daemon.log
```

Preview files:

- `native/desktop-agent/package/macos/config.example.toml`
- `native/desktop-agent/package/macos/com.greycardinal.daemon.plist`
- `native/desktop-agent/package/macos/README_DAEMON_MACOS.md`
- `scripts/package_macos.sh`

macOS packaging needs a macOS runner plus signing/notarization before the DMG or
PKG can be published.

## Backend Ingest

Installers and smoke scripts use:

```text
POST https://fishingteam.su/api/audio/upload
GET  https://fishingteam.su/api/meetings
```

The cockpit shows accepted audio uploads in `Daemon uploads`.

## CI

The release workflow lives at:

```text
.github/workflows/build-daemon-installers.yml
```

It builds the Windows MSI on `windows-latest` and publishes preview docs for
Linux/macOS until native capture/package artifacts are implemented.
