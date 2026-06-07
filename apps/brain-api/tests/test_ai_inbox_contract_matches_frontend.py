from uuid import uuid4

import pytest
from sqlalchemy import func, select

from brain_api.api.routes.grey_board import (
    InboxAssignRequest,
    ai_inbox,
    approve_inbox,
    assign_inbox,
    reject_inbox,
)
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_ai_inbox_contract_matches_frontend(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=user.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Team", timezone="Europe/Moscow"
        )
        item = m.AIInboxItemModel(
            id=uuid4(),
            team_id=team.id,
            kind="needs_assignee",
            status="pending",
            reason="ambiguous_assignee",
            raw_text="Denis, do it",
            confidence=0.72,
            source_type="telegram",
            source_id="42",
            proposed_action="choose_assignee",
        )
        session.add_all([
            user,
            company,
            team,
            m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"),
            item,
        ])
        await session.commit()

        payload = await ai_inbox(team.id, user, session)

    assert list(payload) == ["items"]
    expected = {
        "id": str(item.id),
        "kind": "needs_assignee",
        "status": "pending",
        "reason": "ambiguous_assignee",
        "raw_text": "Denis, do it",
        "confidence": 0.72,
        "suggested_action": "choose_assignee",
    }
    assert expected.items() <= payload["items"][0].items()
    assert payload["items"][0]["source"] == {"type": "telegram", "message_id": "42"}


@pytest.mark.asyncio
async def test_web_approves_daemon_proposal_into_local_grey_board_idempotently(session_factory):
    async with session_factory() as session:
        manager = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com")
        employee = m.UserModel(id=uuid4(), display_name="Employee", email="e@example.com")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=manager.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Team", timezone="Europe/Moscow"
        )
        proposal = m.TaskProposalModel(
            id=uuid4(),
            team_id=team.id,
            source="meeting_transcript",
            title="Подготовить релиз",
            assignee_text=manager.display_name,
            assignee_id=manager.id,
            priority="high",
            confidence=0.9,
            raw_text="Подготовить релиз",
            extractor_payload={"kind": "task_candidate"},
        )
        confirmation = m.ConfirmationModel(
            id=uuid4(), team_id=team.id, proposal_id=proposal.id, status="pending"
        )
        item = m.AIInboxItemModel(
            id=uuid4(),
            team_id=team.id,
            kind="task_candidate",
            status="pending",
            source_type="daemon_proposal",
            source_id=str(proposal.id),
            semantic_payload={"task": {"title": proposal.title}},
            confidence=proposal.confidence,
        )
        session.add_all(
            [
                manager,
                employee,
                company,
                team,
                m.TeamMemberModel(
                    id=uuid4(), team_id=team.id, user_id=manager.id, role="manager"
                ),
                m.TeamMemberModel(
                    id=uuid4(), team_id=team.id, user_id=employee.id, role="employee"
                ),
                proposal,
                confirmation,
                item,
            ]
        )
        await session.commit()

        await assign_inbox(item.id, InboxAssignRequest(user_id=employee.id), manager, session)
        first = await approve_inbox(item.id, manager, session)
        second = await approve_inbox(item.id, manager, session)

        assert first == second
        assert first["sync_status"] == "local_only"
        assert await session.scalar(select(func.count()).select_from(m.TaskModel)) == 1
        await session.refresh(item)
        await session.refresh(confirmation)
        task = await session.get(m.TaskModel, item.linked_task_id)
        assert task is not None
        assert task.created_from_proposal_id == proposal.id
        assert task.assignee_id == employee.id
        assert proposal.assignee_id == employee.id
        assert item.status == "approved"
        assert confirmation.status == "accepted"
        assert confirmation.created_task_id == task.id


@pytest.mark.asyncio
async def test_web_rejects_daemon_confirmation(session_factory):
    async with session_factory() as session:
        manager = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=manager.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Team", timezone="Europe/Moscow"
        )
        proposal = m.TaskProposalModel(
            id=uuid4(),
            team_id=team.id,
            source="meeting_transcript",
            title="Не создавать",
            priority="medium",
            confidence=0.8,
            raw_text="Не создавать",
            extractor_payload={},
        )
        confirmation = m.ConfirmationModel(
            id=uuid4(), team_id=team.id, proposal_id=proposal.id, status="pending"
        )
        item = m.AIInboxItemModel(
            id=uuid4(),
            team_id=team.id,
            status="pending",
            source_type="daemon_proposal",
            source_id=str(proposal.id),
        )
        session.add_all(
            [
                manager,
                company,
                team,
                m.TeamMemberModel(
                    id=uuid4(), team_id=team.id, user_id=manager.id, role="manager"
                ),
                proposal,
                confirmation,
                item,
            ]
        )
        await session.commit()

        assert await reject_inbox(item.id, manager, session) == {"status": "rejected"}
        await session.refresh(confirmation)
        assert confirmation.status == "rejected"
