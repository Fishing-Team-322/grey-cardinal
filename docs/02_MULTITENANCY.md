# Multitenancy

The tenant boundary is `company_id` and `team_id`.

Rules:

- A director owns company-level administration through `company_admins`.
- Managers and employees are scoped through `team_members`.
- Every team object stores `company_id`.
- Every task, meeting, report, absence, board card, reminder, and digest is team-scoped.
- APIs with `company_id` or `team_id` must pass RBAC helpers before reading or mutating data.

v2 intentionally does not implement a user belonging to multiple companies.
