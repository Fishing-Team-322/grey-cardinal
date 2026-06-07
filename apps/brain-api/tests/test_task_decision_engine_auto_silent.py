from uuid import uuid4

from brain_api.application.agentic_tasks import (
    AssigneeResolution,
    InteractionMode,
    TaskDecisionEngine,
)


def _semantic(**overrides):
    result = {
        "kind": "task_candidate",
        "confidence": 0.9,
        "business_relevance": 0.9,
        "is_actionable": True,
        "is_abusive": False,
        "is_vague": False,
        "task": {"title": "Подготовить отчёт", "action_object": "отчёт"},
    }
    result.update(overrides)
    return result


def test_auto_unresolved_assignee_goes_to_inbox_without_clarification():
    decision = TaskDecisionEngine().decide(
        semantic_result=_semantic(),
        identity_resolution=AssigneeResolution(status="unresolved", raw_reference="Пенис"),
        interaction_mode=InteractionMode.AUTO_BACKGROUND,
        has_context=False,
    )
    assert decision.action == "create_ai_inbox_item"
    assert decision.reason == "needs_assignee"


def test_explicit_mode_can_ask_for_assignee():
    decision = TaskDecisionEngine().decide(
        semantic_result=_semantic(confidence=0.6),
        identity_resolution=AssigneeResolution(status="unresolved", raw_reference="Пенис"),
        interaction_mode=InteractionMode.EXPLICIT_TASK_COMMAND,
        has_context=False,
    )
    assert decision.action == "ask_clarification"


def test_abusive_non_business_message_is_ignored():
    decision = TaskDecisionEngine().decide(
        semantic_result=_semantic(is_abusive=True, business_relevance=0.1),
        identity_resolution=AssigneeResolution(
            status="resolved", user_id=uuid4(), display_name="Денис"
        ),
        interaction_mode=InteractionMode.AUTO_BACKGROUND,
        has_context=False,
    )
    assert decision.action == "ignore"
