"""Фейковые LLM-провайдеры/фабрика для тестов semantic-пайплайна.

Никаких реальных HTTP-вызовов: провайдер либо возвращает заранее заданный
ответ, либо кидает указанную ошибку. Это позволяет проверять fallback / retry /
schema-валидацию детерминированно.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from brain_api.infrastructure.llm.providers import ResolvedLLM


@dataclass
class FakeConfig:
    max_retries: int = 2
    model: str = "fake-model"
    base_url: str = "https://fake.local/v1"
    provider: str = "external_api"

    @property
    def label(self) -> str:
        return "fake"


class FakeProvider:
    """Провайдер, отдающий ответы из очереди behaviours.

    Каждый элемент behaviours — либо dict (вернуть), либо Exception (бросить),
    либо callable() -> dict. Когда очередь кончилась, повторяется последний.
    """

    def __init__(self, behaviours: list, *, max_retries: int = 2) -> None:
        self._behaviours = behaviours
        self.config = FakeConfig(max_retries=max_retries)
        self.calls = 0

    async def complete_json(
        self, prompt: str, schema_name: str, *, json_schema: dict | None = None
    ) -> dict:
        self.calls += 1
        index = min(self.calls - 1, len(self._behaviours) - 1)
        behaviour = self._behaviours[index]
        if isinstance(behaviour, Exception):
            raise behaviour
        if isinstance(behaviour, Callable):  # type: ignore[arg-type]
            return behaviour()
        return behaviour


class FakeFactory:
    """Фабрика, возвращающая фиксированную пару primary/fallback."""

    def __init__(self, primary: FakeProvider, fallback: FakeProvider | None = None) -> None:
        self._primary = primary
        self._fallback = fallback

    async def resolve_for_team(self, team_id) -> ResolvedLLM:
        return ResolvedLLM(primary=self._primary, fallback=self._fallback)
