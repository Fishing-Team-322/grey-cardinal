# Desktop-First Audio Architecture

Grey Cardinal is moving away from one mixed system-audio daemon as the production source of truth.

## Why Not System Audio

System loopback captures everything: meeting speech, browser audio, music, videos, and notification sounds. It also gives the server a mixed stream where speaker identity must be guessed. That is useful for demos and diagnostics, but it is the wrong production trust model.

## Identity Rule

Speaker identity is not voice recognition.

```text
Petya is Petya because:
- Petya is logged into the desktop app
- the transcript came from Petya's registered device/session
- the capture mode is microphone
```

The trusted desktop transcript shape is:

```text
source.kind = desktop_app
source.user_id = authenticated user
source.device_id = registered device
source.client_session_id = active session
source.capture_mode = microphone

speaker.identity_source = authenticated_client
speaker.identity_confidence = 1.0
```

## Flow

```text
Desktop App user microphone
  -> POST /desktop/transcripts
  -> brain-api trusted meeting timeline
  -> task proposal
  -> Telegram/Desktop confirmation
  -> task lifecycle
  -> gamification state
```

Each participant installs the desktop app. The meeting timeline is assembled from multiple authenticated microphone clients, not one mixed room/system stream.

## Brain API Ownership

`brain-api` owns devices, client sessions, meeting participants, transcript ingest, extraction, task lifecycle, board integration, reminders, websocket events, and gamification. The desktop app never talks directly to PostgreSQL or YouGile.

## Self-Assignment

When Petya's authenticated desktop client sends:

```text
Я подготовлю оплату до завтра
```

the proposal assignee is Petya with server-side trusted identity. If Petya says:

```text
Аня, проверь интеграцию с YouGile сегодня вечером
```

the extractor may assign Anya if she is a known workspace user. If no executor is explicit and there is no self-reference, assignee stays unknown.

## Telegram, Audio Worker, Native Agent

Telegram remains the notification, confirmation, reminder, and demo fallback channel.

`audio-worker` remains a legacy/mock pipeline that posts `/internal/audio/transcript`. It is not the production speaker identity source.

`native/desktop-agent` still contains the Windows WASAPI loopback MVP, but that mode is explicitly `system_loopback_experimental`. The production default capture mode is `microphone`; the desktop app mock microphone path is the current desktop-first skeleton.

## Fallbacks

Allowed optional modes:

- `microphone`
- `system_loopback_experimental`
- `mixed_meeting_experimental`
- `mock`

Only authenticated desktop microphone transcripts are trusted for speaker identity.
