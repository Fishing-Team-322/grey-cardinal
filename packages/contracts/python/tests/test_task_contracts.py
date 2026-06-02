from grey_cardinal_contracts import TaskExtractionResult, TaskPriority, TaskStatus


def test_task_extraction_defaults_are_stable():
    result = TaskExtractionResult(has_task=False)
    assert result.priority == TaskPriority.medium
    assert result.confidence == 0.0


def test_task_status_values_cover_p0_lifecycle():
    assert {status.value for status in TaskStatus} >= {"todo", "in_progress", "blocked", "done"}
