"""Базовые типы board-адаптеров.

Контракт BoardGateway определён как Protocol в application.ports. Здесь —
конфиг YouGile и фабрика, выбирающая адаптер по BOARD_PROVIDER.
"""

from __future__ import annotations

from dataclasses import dataclass

from brain_api.domain.enums import BoardProvider, TaskStatus


@dataclass(frozen=True, slots=True)
class YouGileConfig:
    api_base_url: str
    api_key: str
    company_id: str | None = None
    project_id: str | None = None
    board_id: str | None = None
    column_backlog_id: str | None = None
    column_todo_id: str | None = None
    column_in_progress_id: str | None = None
    column_review_id: str | None = None
    column_blocked_id: str | None = None
    column_done_id: str | None = None

    def column_for(self, status: TaskStatus) -> str | None:
        return {
            TaskStatus.todo: self.column_todo_id,
            TaskStatus.in_progress: self.column_in_progress_id,
            TaskStatus.blocked: self.column_blocked_id,
            TaskStatus.done: self.column_done_id,
        }.get(status)

    @property
    def is_configured(self) -> bool:
        return not self.missing_required

    @property
    def missing_required(self) -> list[str]:
        required = {
            "YOUGILE_API_KEY": self.api_key,
            "YOUGILE_COMPANY_ID": self.company_id,
            "YOUGILE_PROJECT_ID": self.project_id,
            "YOUGILE_BOARD_ID": self.board_id,
            "YOUGILE_COLUMN_TODO_ID": self.column_todo_id,
        }
        return [name for name, value in required.items() if not value]


def resolve_provider(value: str) -> BoardProvider:
    try:
        return BoardProvider(value)
    except ValueError:
        return BoardProvider.mock
