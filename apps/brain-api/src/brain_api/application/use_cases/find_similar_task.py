"""Use case: поиск похожей активной задачи (детекция дублей, P0-эвристика).

Перед созданием нового proposal мы проверяем, нет ли уже активной задачи на ту
же тему у того же исполнителя с близким дедлайном. Если есть — не плодим дубль.

Похожесть считается без эмбеддингов: нормализация заголовка + token overlap,
плюс бонусы за совпадение исполнителя, близость дедлайна и общий проект.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from brain_api.application.config import AppConfig
from brain_api.application.ports import UnitOfWork
from brain_api.domain.entities import Task

# Стоп-слова/стемы: служебные части речи и обобщённые глаголы-поручения, которые
# не несут смысла темы задачи. Совпадение по префиксу (учитывает окончания).
_STOP_STEMS: tuple[str, ...] = (
    "сдела", "сделай", "надо", "нужно", "провер", "подготов", "оформ",
    "залить", "выложи", "обнов", "реализ", "запили", "закры", "закрой",
    "задач", "карточк", "это", "как-нибудь",
)
# Короткие стоп-слова — сравниваем целиком (предлоги/частицы).
_STOP_WORDS: frozenset[str] = frozenset(
    {"до", "к", "в", "по", "на", "от", "с", "из", "за", "бы", "же", "и", "а", "у", "о"}
)

_PUNCT_RE = re.compile(r"[^\w\s-]", flags=re.UNICODE)


@dataclass(slots=True)
class SimilarTaskResult:
    """Результат поиска дубля."""

    is_duplicate: bool
    task: Task | None
    score: float


def normalize_title(title: str) -> list[str]:
    """lower -> убрать пунктуацию -> токенизация -> выкинуть стоп-слова."""
    cleaned = _PUNCT_RE.sub(" ", title.lower())
    tokens: list[str] = []
    for raw in cleaned.split():
        token = raw.strip("-")
        if not token or token in _STOP_WORDS:
            continue
        if any(token.startswith(stem) for stem in _STOP_STEMS):
            continue
        tokens.append(token)
    return tokens


def _token_overlap(a: list[str], b: list[str]) -> float:
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        # После выкидывания стоп-слов один из заголовков пуст — сравним сырые.
        return 0.0
    intersection = set_a & set_b
    return len(intersection) / min(len(set_a), len(set_b))


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def _assignee_score(
    new_id: UUID | None, new_text: str | None, task: Task
) -> float:
    if new_id is not None and task.assignee_id is not None:
        return 1.0 if new_id == task.assignee_id else 0.0
    a = (new_text or "").strip().lstrip("@").lower()
    b = (task.assignee_text or "").strip().lstrip("@").lower()
    if a and b:
        return 1.0 if (a == b or a in b or b in a) else 0.0
    return 0.5  # одна сторона неизвестна — не штрафуем сильно


def _deadline_score(new_deadline: datetime | None, task_deadline: datetime | None) -> float:
    if new_deadline is not None and task_deadline is not None:
        diff = abs(_naive(new_deadline) - _naive(task_deadline))
        if diff <= timedelta(hours=24):
            return 1.0
        if diff <= timedelta(hours=72):
            return 0.5
        return 0.0
    if new_deadline is None and task_deadline is None:
        return 0.5
    return 0.3


def _project_score(new_project_id: UUID | None, task_project_id: UUID | None) -> float:
    if new_project_id is None or task_project_id is None:
        return 0.5
    return 1.0 if new_project_id == task_project_id else 0.0


def score_similarity(
    *,
    title: str,
    assignee_id: UUID | None,
    assignee_text: str | None,
    deadline: datetime | None,
    project_id: UUID | None,
    task: Task,
) -> float:
    """Итоговый score [0..1] похожести нового proposal на существующую задачу."""
    token = _token_overlap(normalize_title(title), normalize_title(task.title))
    assignee = _assignee_score(assignee_id, assignee_text, task)
    deadline_s = _deadline_score(deadline, task.deadline)
    project = _project_score(project_id, task.project_id)
    return round(
        0.5 * token + 0.25 * assignee + 0.15 * deadline_s + 0.10 * project, 4
    )


class FindSimilarTask:
    def __init__(self, uow: UnitOfWork, config: AppConfig) -> None:
        self._uow = uow
        self._config = config

    async def execute(
        self,
        title: str,
        assignee_id: UUID | None,
        assignee_text: str | None,
        deadline: datetime | None,
        project_id: UUID | None,
    ) -> SimilarTaskResult:
        # Сравниваем только активные задачи (todo / in_progress / blocked).
        active = await self._uow.tasks.list_active()
        threshold = self._config.duplicate_similarity_threshold

        best_task: Task | None = None
        best_score = 0.0
        for task in active:
            score = score_similarity(
                title=title,
                assignee_id=assignee_id,
                assignee_text=assignee_text,
                deadline=deadline,
                project_id=project_id,
                task=task,
            )
            if score > best_score:
                best_score = score
                best_task = task

        is_duplicate = best_task is not None and best_score >= threshold
        return SimilarTaskResult(
            is_duplicate=is_duplicate,
            task=best_task if is_duplicate else None,
            score=best_score,
        )
