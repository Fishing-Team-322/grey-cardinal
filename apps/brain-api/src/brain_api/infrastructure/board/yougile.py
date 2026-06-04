"""YouGileBoardGateway — адаптер к YouGile REST API v2.

Реализован полноценно для create/move/close; add_comment — best-effort. Любая
сетевая/HTTP-ошибка превращается в доменную BoardError, чтобы вызывающий
use case записал её в audit_log и НЕ потерял локальную задачу.

Документация API: https://ru.yougile.com/api-v2
"""

from __future__ import annotations

import logging

import httpx

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskStatus
from brain_api.domain.errors import BoardError
from brain_api.infrastructure.board.base import YouGileConfig
from grey_cardinal_contracts import BoardCardResult, BoardProvider

logger = logging.getLogger(__name__)


class YouGileBoardGateway:
    def __init__(self, config: YouGileConfig, timeout: float = 20.0) -> None:
        if not config.is_configured:
            raise ValueError("YouGile is not configured: " + ", ".join(config.missing_required))
        self._config = config
        self._timeout = timeout
        self._base = config.api_base_url.rstrip("/") + "/api-v2"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._config.api_key}"}

    async def create_card(self, task: Task) -> BoardCardResult:
        column_id = self._config.column_todo_id
        body = {
            "title": f"{task.public_id} {task.title}".strip(),
            "columnId": column_id,
            "description": _description(task),
        }
        data = await self._request("POST", "/tasks", json=body)
        external_id = str(data.get("id"))
        if not external_id or external_id == "None":
            raise BoardError(f"YouGile вернул некорректный ответ создания: {data}")
        return BoardCardResult(
            provider=BoardProvider.yougile,
            external_card_id=external_id,
            external_url=None,
            external_payload=data,
        )

    async def move_card(self, external_card_id: str, status: TaskStatus) -> None:
        column_id = self._config.column_for(status)
        if column_id is None:
            logger.info("YouGile: для статуса %s не задана колонка, пропуск", status.value)
            return
        await self._request("PUT", f"/tasks/{external_card_id}", json={"columnId": column_id})

    async def close_card(self, external_card_id: str) -> None:
        body: dict = {"completed": True}
        done_column = self._config.column_done_id
        if done_column:
            body["columnId"] = done_column
        await self._request("PUT", f"/tasks/{external_card_id}", json=body)

    async def add_comment(self, external_card_id: str, text: str) -> None:
        # Комментарии в YouGile — сообщения в чате задачи. Best-effort.
        try:
            await self._request(
                "POST", f"/tasks/{external_card_id}/chat-messages", json={"text": text}
            )
        except BoardError as exc:
            logger.info("YouGile add_comment best-effort failed: %s", exc)

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        url = self._base + path
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, json=json, headers=self._headers())
                response.raise_for_status()
                if response.content:
                    return response.json()
                return {}
        except httpx.HTTPStatusError as exc:
            raise BoardError(
                f"YouGile {method} {path} -> {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BoardError(f"YouGile {method} {path} сетевая ошибка: {exc}") from exc


def _description(task: Task) -> str:
    parts = []
    if task.assignee_text:
        parts.append(f"Ответственный: {task.assignee_text}")
    if task.deadline:
        parts.append(f"Дедлайн: {task.deadline.isoformat()}")
    parts.append(f"Источник: {task.source.value}")
    parts.append("Создано Grey Cardinal")
    return "\n".join(parts)
