# Timezones

Company timezone is required in production during company creation.

Frontend can suggest:

```ts
Intl.DateTimeFormat().resolvedOptions().timeZone
```

Backend validates IANA timezone names with `zoneinfo.ZoneInfo`.

Team creation rule:

- explicit team timezone wins;
- otherwise team inherits `company.timezone`.

Relative deadlines, meetings, evening digest, and team reminders are interpreted in `team.timezone`. Personal notifications can use `users.timezone` when set.
