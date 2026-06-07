# Director overview

Endpoint:

```text
GET /api/companies/{id}/overview
```

Access: company `director` only.

The response contains:

- company identity and timezone;
- total team count;
- open tasks;
- overdue tasks;
- completed tasks in the last 7 days;
- per-team summary;
- hotspots for overdue work.

This endpoint is the director's cross-team operational surface.
