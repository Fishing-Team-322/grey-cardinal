# ruff: noqa: E501
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher


class FullFakeYouGile:
    def __init__(self) -> None:
        self.projects = [{"id": "p1", "title": "Product"}]
        self.boards = [{"id": "b1", "title": "Backend Board", "projectId": "p1"}]
        self.columns = [
            {"id": "c1", "title": "Todo", "boardId": "b1"},
            {"id": "c2", "title": "In Progress", "boardId": "b1"},
            {"id": "c3", "title": "Done", "boardId": "b1"},
        ]
        self.tasks = {
            "c1": [
                {
                    "id": "yt1",
                    "title": "Import task",
                    "columnId": "c1",
                    "description": "From YouGile",
                    "deadline": {"deadline": int((datetime.now(UTC) + timedelta(days=1)).timestamp() * 1000)},
                    "assigned": ["yu1"],
                }
            ]
        }
        self.users = [{"id": "yu1", "email": "employee@example.com", "realName": "Employee"}]
        self.created = []
        self.updated = []

    async def health(self):
        return {"ok": True}

    async def list_projects(self):
        return self.projects

    async def list_boards(self, project_id=None):
        return [item for item in self.boards if not project_id or item.get("projectId") == project_id]

    async def list_columns(self, board_id=None):
        return [item for item in self.columns if not board_id or item.get("boardId") == board_id]

    async def list_tasks(self, board_id=None, cursor=None, *, column_id=None, assigned_to=None):
        if column_id:
            return list(self.tasks.get(column_id, []))
        return [task for rows in self.tasks.values() for task in rows]

    async def list_users(self):
        return self.users

    async def create_task(self, title, column_id, **fields):
        payload = {"id": f"created-{len(self.created) + 1}", "title": title, "columnId": column_id, **fields}
        self.created.append(payload)
        self.tasks.setdefault(column_id, []).append(payload)
        return payload

    async def update_task(self, task_id, **fields):
        self.updated.append((task_id, fields))
        return {"id": task_id, **fields}


async def seed_pm(session_factory):
    cipher = SecretCipher("dev-key")
    async with session_factory() as session:
        director = m.UserModel(id=uuid4(), display_name="Director", email="director@example.com", login="director")
        employee = m.UserModel(id=uuid4(), display_name="Employee", email="employee@example.com", login="employee")
        company = m.CompanyModel(id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=director.id)
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Backend",
            timezone="Europe/Moscow",
            board_provider="yougile",
            board_credentials_encrypted=cipher.encrypt_text(json.dumps({"api_key": "fake"})),
        )
        session.add_all([director, employee, company, team])
        await session.flush()
        session.add_all(
            [
                m.CompanyAdminModel(id=uuid4(), company_id=company.id, user_id=director.id, role="director"),
                m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=director.id, role="manager"),
                m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=employee.id, role="employee"),
                m.YouGileConnectionModel(
                    id=uuid4(),
                    team_id=team.id,
                    provider="yougile",
                    credentials_encrypted=team.board_credentials_encrypted,
                    status="active",
                ),
            ]
        )
        await session.commit()
        return {"director_id": director.id, "employee_id": employee.id, "company_id": company.id, "team_id": team.id, "cipher": cipher}
