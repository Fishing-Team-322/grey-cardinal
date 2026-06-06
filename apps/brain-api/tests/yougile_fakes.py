"""Stateful in-memory fake of YouGileClient for discovery/onboarding tests."""

from __future__ import annotations

from typing import Any


class FakeYouGile:
    def __init__(
        self,
        *,
        projects: list[dict] | None = None,
        boards: list[dict] | None = None,
        columns: list[dict] | None = None,
        tasks: dict[str, list[dict]] | None = None,
        users: list[dict] | None = None,
        companies: list[dict] | None = None,
        keys: list[dict] | None = None,
    ) -> None:
        self._projects = projects if projects is not None else []
        self._boards = boards or []
        self._columns = columns or []
        self._tasks = tasks or {}  # column_id -> [task]
        self._users = users or []
        self._companies = companies or [{"id": "co1", "name": "Acme"}]
        self._keys = keys if keys is not None else [{"key": "existing-key"}]
        self.created: dict[str, list] = {
            "project": [],
            "board": [],
            "column": [],
            "task": [],
            "webhook": [],
        }
        self.rate_limit_remaining = 50

    # auth
    async def auth_companies(self, login, password):  # noqa: ANN001
        return self._companies

    async def auth_keys_get(self, login, password, company_id):  # noqa: ANN001
        return self._keys

    async def auth_keys_create(self, login, password, company_id):  # noqa: ANN001
        return "newly-created-key"

    # resources
    async def list_projects(self):
        return self._projects

    async def list_boards(self, project_id=None):  # noqa: ANN001
        return [b for b in self._boards if not project_id or b.get("projectId") == project_id]

    async def list_columns(self, board_id=None):  # noqa: ANN001
        return [c for c in self._columns if not board_id or c.get("boardId") == board_id]

    async def list_tasks(self, *, column_id=None, assigned_to=None):  # noqa: ANN001
        return list(self._tasks.get(column_id, []))

    async def list_users(self):
        return self._users

    async def create_project(self, title, users=None):  # noqa: ANN001
        p = {"id": f"p-{len(self.created['project']) + 1}", "title": title}
        self._projects.append(p)
        self.created["project"].append(p)
        return p

    async def create_board(self, title, project_id):  # noqa: ANN001
        b = {"id": f"b-{len(self.created['board']) + 1}", "title": title, "projectId": project_id}
        self._boards.append(b)
        self.created["board"].append(b)
        return b

    async def create_column(self, title, board_id, color=1):  # noqa: ANN001
        c = {"id": f"c-{len(self.created['column']) + 1}", "title": title, "boardId": board_id}
        self._columns.append(c)
        self.created["column"].append(c)
        return c

    async def create_task(self, title, column_id, **kw):  # noqa: ANN001
        t = {
            "id": f"t-{len(self.created['task']) + 1}",
            "title": title,
            "columnId": column_id,
            **kw,
        }
        self._tasks.setdefault(column_id, []).append(t)
        self.created["task"].append(t)
        return t

    async def update_task(self, task_id, **fields: Any):
        return {"id": task_id, **fields}

    async def create_webhook(self, url, event):  # noqa: ANN001
        wh = {"id": f"wh-{len(self.created['webhook']) + 1}", "url": url, "event": event}
        self.created["webhook"].append(wh)
        return wh

    async def list_webhooks(self):
        return list(self.created["webhook"])

    async def disable_webhook(self, webhook_id):  # noqa: ANN001
        return {"id": webhook_id, "disabled": True}
