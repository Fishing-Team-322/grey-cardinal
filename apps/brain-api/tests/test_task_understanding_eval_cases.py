import json
from pathlib import Path


def test_task_understanding_eval_dataset_contains_required_regressions():
    path = (
        Path(__file__).parents[1]
        / "evals"
        / "task_understanding_cases_ru.jsonl"
    )
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    by_text = {case["text"]: case for case in cases}

    assert by_text["Денису подготовить отчёт до завтра"]["expected_assignee"] == "Денис"
    assert by_text["Денису сходить нахуй до сегодняшнего вечера"]["expected_action"] == "ignore"
    assert by_text["Denis, complete the task"]["expected_action"] == "ignore_or_ai_inbox"
    assert by_text["/task Пенис сделать задачу"]["expected_action"] == "ask_assignee"
