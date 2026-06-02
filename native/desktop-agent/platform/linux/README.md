# Linux Audio Adapter Plan

P0 is Windows-only. The common agent core is ready for a future Linux adapter that implements `IAudioCapture`.

Likely paths:

- PipeWire monitor stream for modern desktops.
- PulseAudio monitor source fallback for older environments.

The adapter should keep Linux-specific headers and linking in `platform/linux`, then feed PCM frames into the existing chunker/uploader without changing config, logging, WAV writing, or HTTP code.

