# RBAC

v2 authorization is centered on `TenantContext`.

Helpers:

- `require_company_role(ctx, company_id, "director")`
- `require_team_member(ctx, team_id)`
- `require_team_role(ctx, team_id, "manager")`

Company APIs:

- create company: authenticated.
- company overview: director.
- create team: director.
- company invites: director.

Team APIs:

- details/tasks/status: team member.
- invites/board/LLM settings: manager.
