# Grey Cardinal Desktop App

Desktop-first client skeleton for authenticated microphone transcript flow.

The desktop app is the primary participant client. Telegram remains a notification and confirmation channel; `audio-worker` remains a legacy/dev path.

## Dev Run

```powershell
cd apps\desktop-app
npm install
npm run build
npm run dev
```

Expected backend:

```powershell
docker compose --profile full up --build
```

or local `brain-api` on `http://localhost:8010`.

## Flow

1. Register a dev identity/device.
2. Join a meeting such as `MTG-1`.
3. Start mock microphone.
4. Send a mock phrase through `POST /desktop/transcripts`.
5. Review transcript, task list, and gamification state.

The mock microphone flow uses authenticated desktop identity and `capture_mode=microphone`. It does not use voice recognition as source of truth.
