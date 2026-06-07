# Следующие этапы

После P0 остаются:

- проверить onboarding и двустороннюю синхронизацию YouGile на тестовой команде;
- production auth и rotation internal token;
- заменить hackathon desktop dev-auth на OAuth/JWT и refresh sessions;
- подключить реальный microphone capture/ASR в desktop app или companion daemon;
- outbox/retry для board и Telegram side effects;
- реальный ASR и VAD в microphone pipeline;
- diarization оставить optional analytics, не source of truth для identity;
- Linux/macOS capture adapters;
- dashboard UX и production deployment;
- нагрузочные проверки конкурентных confirm callback.
