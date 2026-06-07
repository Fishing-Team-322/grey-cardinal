"""Interaction policy, identity resolution, and context-aware task decisions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import TelegramEntity


class InteractionMode(StrEnum):
    AUTO_BACKGROUND = "AUTO_BACKGROUND"
    EXPLICIT_TASK_COMMAND = "EXPLICIT_TASK_COMMAND"
    REPLY_TASK_COMMAND = "REPLY_TASK_COMMAND"
    CALLBACK_ACTION = "CALLBACK_ACTION"
    WEB_MANUAL = "WEB_MANUAL"
    SYNC_REPORT = "SYNC_REPORT"


@dataclass(frozen=True)
class AssigneeCandidate:
    user_id: UUID
    display_name: str
    confidence: float
    source: str


@dataclass(frozen=True)
class AssigneeResolution:
    status: Literal["resolved", "unresolved", "none", "ambiguous"]
    user_id: UUID | None = None
    display_name: str | None = None
    source: str = "none"
    confidence: float = 0.0
    candidates: list[AssigneeCandidate] = field(default_factory=list)
    raw_reference: str | None = None

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["user_id"] = str(self.user_id) if self.user_id else None
        for candidate in value["candidates"]:
            candidate["user_id"] = str(candidate["user_id"])
        return value


def normalize_alias(value: str) -> str:
    value = value.strip().lower().lstrip("@")
    value = value.replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", value)


def generated_aliases(display_name: str, username: str | None = None) -> set[str]:
    aliases = {display_name}
    first = display_name.strip().split()[0] if display_name.strip() else ""
    if first:
        aliases.add(first)
        lower = first.lower()
        # Common Russian dative forms are identity aliases, not task semantics.
        if lower.endswith(("с", "н", "р", "л", "м", "т", "й")):
            aliases.add(f"{first}у")
        if lower.endswith("я"):
            aliases.add(f"{first[:-1]}е")
        if lower.endswith("а"):
            aliases.add(f"{first[:-1]}е")
    if username:
        aliases.update({username, f"@{username}"})
    return {alias for alias in aliases if normalize_alias(alias)}


class IdentityResolver:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_team_aliases(self, team_id: UUID) -> None:
        rows = (
            await self._session.execute(
                select(m.UserModel)
                .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                .where(m.TeamMemberModel.team_id == team_id)
            )
        ).scalars()
        existing = {
            item.normalized_alias
            for item in (
                await self._session.execute(
                    select(m.UserAliasModel).where(m.UserAliasModel.team_id == team_id)
                )
            ).scalars()
        }
        for user in rows:
            for alias in generated_aliases(user.display_name, user.telegram_username):
                normalized = normalize_alias(alias)
                if normalized in existing:
                    continue
                self._session.add(
                    m.UserAliasModel(
                        team_id=team_id,
                        user_id=user.id,
                        alias=alias,
                        normalized_alias=normalized,
                        source="telegram" if "@" in alias else "auto",
                        confidence=1.0,
                    )
                )
                existing.add(normalized)
        await self._session.flush()

    async def resolve_assignee(
        self,
        team_id: UUID,
        assignee_reference: str | None,
        telegram_entities: list[TelegramEntity],
        message_text: str,
        reply_to_sender_id: UUID | None,
        interaction_mode: InteractionMode,
    ) -> AssigneeResolution:
        members = list(
            (
                await self._session.execute(
                    select(m.UserModel)
                    .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                    .where(m.TeamMemberModel.team_id == team_id)
                )
            ).scalars()
        )
        by_tg = {user.telegram_user_id: user for user in members if user.telegram_user_id}
        by_username = {
            normalize_alias(user.telegram_username): user
            for user in members
            if user.telegram_username
        }

        for entity in telegram_entities:
            if entity.type == "text_mention" and entity.user and entity.user.id in by_tg:
                return _resolved(by_tg[entity.user.id], "telegram_text_mention", 1.0)
        for entity in telegram_entities:
            if entity.type == "mention":
                username = normalize_alias(_entity_text(message_text, entity))
                if username in by_username:
                    return _resolved(by_username[username], "telegram_username", 1.0)
        if reply_to_sender_id is not None:
            user = next((item for item in members if item.id == reply_to_sender_id), None)
            if user is not None:
                return _resolved(user, "reply_to_sender", 0.99)

        reference = normalize_alias(assignee_reference or "")
        if not reference:
            return AssigneeResolution(status="none", raw_reference=assignee_reference)

        await self.ensure_team_aliases(team_id)
        aliases = list(
            (
                await self._session.execute(
                    select(m.UserAliasModel, m.UserModel)
                    .join(m.UserModel, m.UserModel.id == m.UserAliasModel.user_id)
                    .where(m.UserAliasModel.team_id == team_id)
                )
            ).all()
        )
        exact = [(alias, user) for alias, user in aliases if alias.normalized_alias == reference]
        if len(exact) == 1:
            return _resolved(exact[0][1], "alias", float(exact[0][0].confidence))
        if len(exact) > 1:
            return AssigneeResolution(
                status="ambiguous",
                candidates=[
                    AssigneeCandidate(user.id, user.display_name, alias.confidence, "alias")
                    for alias, user in exact
                ],
                raw_reference=assignee_reference,
            )

        yougile = list(
            (
                await self._session.execute(
                    select(m.YouGileMappingModel, m.UserModel)
                    .join(m.UserModel, m.UserModel.id == m.YouGileMappingModel.local_id)
                    .where(
                        m.YouGileMappingModel.team_id == team_id,
                        m.YouGileMappingModel.entity_type == "user",
                    )
                )
            ).all()
        )
        for mapping, user in yougile:
            payload = mapping.payload or {}
            names = (payload.get("realName"), payload.get("name"), payload.get("email"))
            if any(normalize_alias(str(value or "")) == reference for value in names):
                return _resolved(user, "yougile_user", 0.95)

        candidates: list[AssigneeCandidate] = []
        if interaction_mode != InteractionMode.AUTO_BACKGROUND:
            scored: dict[UUID, AssigneeCandidate] = {}
            for alias, user in aliases:
                score = SequenceMatcher(None, reference, alias.normalized_alias).ratio()
                if score >= 0.55 and (
                    user.id not in scored or score > scored[user.id].confidence
                ):
                    scored[user.id] = AssigneeCandidate(
                        user.id, user.display_name, round(score, 3), "llm_reference"
                    )
            candidates = sorted(scored.values(), key=lambda item: item.confidence, reverse=True)[:5]
        return AssigneeResolution(
            status="unresolved",
            candidates=candidates,
            raw_reference=assignee_reference,
        )


@dataclass(frozen=True)
class TaskDecision:
    action: Literal[
        "create_proposal",
        "create_ai_inbox_item",
        "ask_clarification",
        "ignore",
        "duplicate_warning",
        "status_update",
    ]
    reason: str
    confidence: float


class TaskDecisionEngine:
    AUTO_MIN_CONFIDENCE = 0.85
    COMMAND_MIN_CONFIDENCE = 0.45

    def decide(
        self,
        *,
        semantic_result: dict[str, Any],
        identity_resolution: AssigneeResolution,
        interaction_mode: InteractionMode,
        has_context: bool,
        duplicate: bool = False,
    ) -> TaskDecision:
        confidence = float(semantic_result.get("confidence") or 0.0)
        kind = semantic_result.get("kind")
        if kind == "status_update":
            return TaskDecision("status_update", "semantic_status_update", confidence)
        explicit = interaction_mode in {
            InteractionMode.EXPLICIT_TASK_COMMAND,
            InteractionMode.REPLY_TASK_COMMAND,
            InteractionMode.WEB_MANUAL,
        }
        if kind != "task_candidate":
            return TaskDecision("ignore", f"semantic_kind:{kind}", confidence)
        if semantic_result.get("is_abusive") and float(
            semantic_result.get("business_relevance") or 0.0
        ) < 0.55:
            return TaskDecision(
                "ask_clarification" if explicit else "ignore",
                "abusive_without_business_result",
                confidence,
            )
        task = semantic_result.get("task") or {}
        action_object = str(task.get("action_object") or task.get("title") or "").strip()
        vague_object = normalize_alias(action_object) in {"это", "то", "задачу", "thetask", "task"}
        vague = bool(semantic_result.get("is_vague")) or (vague_object and not has_context)
        actionable = bool(semantic_result.get("is_actionable", bool(action_object)))
        relevant = float(semantic_result.get("business_relevance") or 0.0)
        threshold = self.COMMAND_MIN_CONFIDENCE if explicit else self.AUTO_MIN_CONFIDENCE

        if duplicate:
            return TaskDecision(
                "duplicate_warning" if explicit else "create_ai_inbox_item",
                "duplicate_suspected",
                confidence,
            )
        if not actionable or relevant < 0.55 or vague:
            return TaskDecision(
                "ask_clarification" if explicit else "create_ai_inbox_item",
                "needs_task_object",
                confidence,
            )
        if identity_resolution.status in {"unresolved", "ambiguous"}:
            return TaskDecision(
                "ask_clarification" if explicit else "create_ai_inbox_item",
                "needs_assignee",
                confidence,
            )
        if not explicit and identity_resolution.status == "none":
            return TaskDecision(
                "create_ai_inbox_item",
                "needs_assignee",
                confidence,
            )
        if confidence < threshold:
            return TaskDecision(
                "ask_clarification" if explicit else "create_ai_inbox_item",
                "low_confidence",
                confidence,
            )
        return TaskDecision("create_proposal", "policy_passed", confidence)


def _resolved(user: m.UserModel, source: str, confidence: float) -> AssigneeResolution:
    return AssigneeResolution(
        status="resolved",
        user_id=user.id,
        display_name=user.display_name,
        source=source,
        confidence=confidence,
    )


def _entity_text(text: str, entity: TelegramEntity) -> str:
    raw = text.encode("utf-16-le")
    start = entity.offset * 2
    end = start + entity.length * 2
    return raw[start:end].decode("utf-16-le", errors="ignore")
