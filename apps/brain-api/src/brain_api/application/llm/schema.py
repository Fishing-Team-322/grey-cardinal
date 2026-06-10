"""Pydantic-схема результата semantic parsing + JSON Schema для response_format.

Контракт совпадает с тем, что исторически возвращал словарь semantic_message_v2
(`kind / confidence / task / meeting / daily_report / absence / reason`), поэтому
маршрутизация в internal_telegram не меняется. Pydantic нужен для строгой
валидации ответа LLM (см. ТЗ: strict JSON validation).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SemanticKind = Literal[
    "task_candidate",
    "task_reassignment",
    "task_cancellation",
    "meeting_candidate",
    "daily_report",
    "absence_notice",
    "status_update",
    "question",
    "noise",
    "unknown",
]

SEMANTIC_KINDS: frozenset[str] = frozenset(SemanticKind.__args__)  # type: ignore[attr-defined]


class TaskPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    description: str | None = None
    assignee_text: str | None = None
    assignee_reference: str | None = None
    assignee_reference_type: Literal["name", "username", "pronoun", "none"] = "none"
    action_object: str | None = None
    deadline: str | None = None
    priority: str | None = None


class MeetingPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    scheduled_at: str | None = None
    duration_minutes: int | None = None


class DailyReportPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str | None = None
    detected_status: str | None = None


class AbsencePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reason: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None


class ReassignmentPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task_reference: str | None = None
    new_assignee_reference: str | None = None
    new_assignee_reference_type: Literal["name", "username", "pronoun", "none"] = "none"


class CancellationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task_reference: str | None = None


class AffectPayload(BaseModel):
    """Эмоциональная окраска сообщения (для эмоционального портрета отдела)."""

    model_config = ConfigDict(extra="ignore")
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)  # негатив..позитив
    stress: float = Field(default=0.0, ge=0.0, le=1.0)
    dominant_emotion: str | None = None


class SemanticParseResult(BaseModel):
    """Строго валидируемый результат semantic parsing."""

    model_config = ConfigDict(extra="ignore")

    kind: SemanticKind
    confidence: float = Field(ge=0.0, le=1.0)
    # Defaults keep compatibility with local/test providers that ignore
    # response_format. The JSON Schema sent to production providers still
    # requires every policy field.
    business_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    is_actionable: bool = False
    is_abusive: bool = False
    is_vague: bool = False
    should_create_proposal: bool = False
    task: TaskPayload | None = None
    meeting: MeetingPayload | None = None
    daily_report: DailyReportPayload | None = None
    absence: AbsencePayload | None = None
    reassignment: ReassignmentPayload | None = None
    cancellation: CancellationPayload | None = None
    affect: AffectPayload | None = None
    reason: str = ""

    def to_contract_dict(self) -> dict:
        """Привести к словарю-контракту, который ждёт internal_telegram."""
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "business_relevance": self.business_relevance,
            "is_actionable": self.is_actionable,
            "is_abusive": self.is_abusive,
            "is_vague": self.is_vague,
            "should_create_proposal": self.should_create_proposal,
            "task": self.task.model_dump() if self.task else None,
            "meeting": self.meeting.model_dump() if self.meeting else None,
            "daily_report": self.daily_report.model_dump() if self.daily_report else None,
            "absence": self.absence.model_dump() if self.absence else None,
            "reassignment": self.reassignment.model_dump() if self.reassignment else None,
            "cancellation": self.cancellation.model_dump() if self.cancellation else None,
            "affect": self.affect.model_dump() if self.affect else None,
            "reason": self.reason,
        }


def semantic_json_schema() -> dict:
    """JSON Schema для response_format={"type":"json_schema", ...}.

    Намеренно нестрогая (``strict`` не выставляем), чтобы schema принимали как
    Groq, так и OpenRouter-модели; финальная гарантия — Pydantic-валидация.
    """
    return {
        "name": "semantic_parse_result",
        "schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": sorted(SEMANTIC_KINDS)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "business_relevance": {"type": "number", "minimum": 0, "maximum": 1},
                "is_actionable": {"type": "boolean"},
                "is_abusive": {"type": "boolean"},
                "is_vague": {"type": "boolean"},
                "should_create_proposal": {"type": "boolean"},
                "task": {"type": ["object", "null"]},
                "meeting": {"type": ["object", "null"]},
                "daily_report": {"type": ["object", "null"]},
                "absence": {"type": ["object", "null"]},
                "reassignment": {"type": ["object", "null"]},
                "cancellation": {"type": ["object", "null"]},
                "affect": {"type": ["object", "null"]},
                "reason": {"type": "string"},
            },
            "required": [
                "kind",
                "confidence",
                "business_relevance",
                "is_actionable",
                "is_abusive",
                "is_vague",
                "should_create_proposal",
            ],
        },
    }
