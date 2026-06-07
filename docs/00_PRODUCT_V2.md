# Grey Cardinal v2 product

Grey Cardinal v2 is a production SaaS for team coordination from Telegram chat.

Core hierarchy:

```text
Company -> Team -> User
```

Roles:

- company: `director`
- team: `manager`, `employee`

Main flow:

1. Director creates a company and chooses an IANA timezone.
2. Director creates teams.
3. A manager links a Telegram team chat and YouGile board settings.
4. The bot reads team chat messages in the background.
5. LLM classifies work events.
6. Task and meeting candidates are proposed with confirmation.
7. Confirmed tasks are stored locally and synced to YouGile when configured.
8. Reminders and daily sync use team timezone.
9. Director sees a cross-team overview.

Production does not silently replace missing services with mocks.
