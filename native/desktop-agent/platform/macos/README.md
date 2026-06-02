# macOS Audio Adapter Plan

P0 is Windows-only. The common agent core is ready for a future macOS adapter that implements `IAudioCapture`.

Likely paths:

- ScreenCaptureKit audio capture on modern macOS when app entitlements and permissions are available.
- BlackHole or another virtual audio device for a hackathon-friendly loopback path.

The adapter should output short `AudioFrame` objects using the shared `AudioFormat` contract and keep all macOS framework includes inside `platform/macos`.

