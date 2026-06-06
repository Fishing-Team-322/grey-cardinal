# Board adapters

YouGile is configured per team from the team settings page:

1. A manager enters the YouGile login and password.
2. The server lists available companies and fetches or creates an API key.
3. Only the API key is retained, encrypted with `SecretCipher`.
4. Discovery mirrors projects, boards, columns, tasks, and users.

YouGile API keys must never be placed in `.env`, source files, command-line
arguments, or logs. Disconnected teams use the local mock adapter so local task
creation remains available.

Runtime configuration contains only non-secret integration settings:

```bash
YOUGILE_API_BASE_URL=https://yougile.com/api-v2
YOUGILE_RATE_LIMIT_PER_MINUTE=50
YOUGILE_ONBOARDING_TOKEN_TTL_SECONDS=90
YOUGILE_DISCOVERY_SCHEDULE_HOURS=6
PUBLIC_BASE_URL=https://fishingteam.su
```
