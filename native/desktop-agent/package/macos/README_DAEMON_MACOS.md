# Grey Cardinal Daemon for macOS

Status: preview packaging skeleton.

The target artifact is `grey-cardinal-daemon-macos-universal.dmg` or a signed
`.pkg`, built on a macOS runner. The current native capture implementation is
Windows WASAPI-only, so macOS ScreenCaptureKit/system audio capture is not
published yet.

## Target Install Flow

1. Download the DMG/PKG.
2. Install Grey Cardinal Daemon.
3. Grant Microphone permission.
4. Grant Screen Recording/System Audio permission when system audio capture is enabled.
5. Configure backend URL: `https://fishingteam.su`.
6. Check logs:

```bash
tail -f ~/Library/Logs/GreyCardinal/Daemon.log
```

## Current Limitation

Use the Windows MSI for real capture/upload today. The macOS package flow is
ready for CI, signing, notarization, and future capture implementation.
