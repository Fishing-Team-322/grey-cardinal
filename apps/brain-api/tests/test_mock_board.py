from uuid import uuid4

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskSource, TaskStatus
from brain_api.infrastructure.board.mock import MockBoardGateway


async def test_mock_board_supports_full_lifecycle():
    board = MockBoardGateway()
    task = Task(
        id=uuid4(),
        public_id="GC-1",
        title="Проверить интеграцию",
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
        source=TaskSource.manual,
    )
    card = await board.create_card(task)
    assert card.provider.value == "mock"
    assert card.external_card_id.startswith("mock-")
    await board.move_card(card.external_card_id, TaskStatus.in_progress)
    await board.add_comment(card.external_card_id, "Готово наполовину")
    await board.close_card(card.external_card_id)
