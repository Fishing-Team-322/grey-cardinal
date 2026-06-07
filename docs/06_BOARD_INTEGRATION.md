# Board integration

v2 supports team-scoped YouGile configuration.

Rules:

- Credentials are encrypted before storing in `teams.board_credentials_encrypted`.
- Board config lives in `teams.board_config`.
- Production requires `BOARD_CREDS_ENCRYPTION_KEY`.
- Missing YouGile credentials for a team is a visible failed integration state, not a mock fallback.

`GET /api/teams/{team_id}/integrations/yougile/status` reports integration state.
