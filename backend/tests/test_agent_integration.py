import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from app.core.security import hash_password
from app.domain.models.chat_requests import ChatRequestDB
from app.domain.models.conversations import ConversationDB
from app.domain.models.messages import MessageDB
from app.domain.models.profile import ProfileDB
from app.domain.models.ticket import TicketDB
from app.domain.models.user import UserDB
from app.schemas.agent import AgentAnswerDTO
from app.services.agent_answer_adapter import AgentAnswerAdapter
from app.services.ai_agent_client import AIAgentClientError
from app.services.chat_service import ChatService
from sqlalchemy import func, select

from tests.conftest import TestingSessionLocal

USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONVERSATION_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_agent_integration_data():
    async with TestingSessionLocal() as session:
        session.add(
            UserDB(
                id=USER_ID,
                email="agent-integration@company.com",
                hashed_password=hash_password("password123"),
            )
        )
        await session.flush()
        session.add(
            ProfileDB(
                id=USER_ID,
                display_name="Agent Integration",
                role="EMPLOYEE",
                department="Engineering",
            )
        )
        session.add(
            ConversationDB(
                id=CONVERSATION_ID,
                user_id=USER_ID,
                title="Agent integration",
                state="ACTIVE",
            )
        )
        await session.commit()


async def create_queued_request(question: str) -> uuid.UUID:
    request_id = uuid.uuid4()
    async with TestingSessionLocal() as session:
        session.add(
            ChatRequestDB(
                id=request_id,
                conversation_id=CONVERSATION_ID,
                user_id=USER_ID,
                question=question,
                state="QUEUED",
            )
        )
        await session.commit()
    return request_id


def normal_answer() -> AgentAnswerDTO:
    return AgentAnswerDTO(
        response="Employees receive 12 leave days.",
        intent="hr_question",
        confidence_score=0.92,
        citations=[
            {
                "chunk_id": "leave-policy::0001",
                "source_file": "leave-policy.pdf",
                "title": "Leave Policy",
                "page_start": 2,
                "page_end": 2,
                "category": "leave",
                "is_official_policy": True,
            }
        ],
    )


def test_adapter_generates_stable_citation_ids():
    request_id = uuid.uuid4()
    first = AgentAnswerAdapter.map(normal_answer(), request_id)
    second = AgentAnswerAdapter.map(normal_answer(), request_id)
    assert first.citations[0]["citation_id"] == second.citations[0]["citation_id"]
    assert first.citations[0]["page"] == 2


@pytest.mark.asyncio
async def test_worker_persists_answer_and_is_idempotent(monkeypatch):
    request_id = await create_queued_request("Leave days?")
    query_agent = AsyncMock(return_value=normal_answer())
    monkeypatch.setattr(ChatService, "agent_client", type("Client", (), {"query_agent": query_agent})())

    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "Leave days?", CONVERSATION_ID
    )
    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "Leave days?", CONVERSATION_ID
    )

    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        message_count = await session.scalar(
            select(func.count(MessageDB.id)).where(MessageDB.chat_request_id == request_id)
        )
        assert chat_request.state == "COMPLETED"
        assert chat_request.answer_status == "ANSWERED"
        assert chat_request.citations[0]["source_file"] == "leave-policy.pdf"
        assert message_count == 1
    assert query_agent.await_count == 1


@pytest.mark.asyncio
async def test_worker_maps_clarification(monkeypatch):
    request_id = await create_queued_request("I want leave")
    answer = AgentAnswerDTO(
        response="Which leave type do you mean?",
        intent="ambiguous",
        needs_clarification=True,
        clarifying_question="Annual leave or sick leave?",
    )
    monkeypatch.setattr(
        ChatService,
        "agent_client",
        type("Client", (), {"query_agent": AsyncMock(return_value=answer)})(),
    )

    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "I want leave", CONVERSATION_ID
    )

    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        assert chat_request.state == "CLARIFICATION_REQUIRED"
        assert chat_request.answer is None
        assert chat_request.clarification["question"] == "Annual leave or sick leave?"


@pytest.mark.asyncio
async def test_agent_history_preserves_follow_up_context():
    conversation_id = uuid.uuid4()
    original_request_id = uuid.uuid4()
    async with TestingSessionLocal() as session:
        conversation = ConversationDB(
            id=conversation_id,
            user_id=USER_ID,
            title="Clarification context",
            state="ACTIVE",
        )
        session.add(conversation)
        await session.flush()

        original_user_message_id = uuid.uuid4()
        original_request = ChatRequestDB(
            id=original_request_id,
            conversation_id=conversation_id,
            user_id=USER_ID,
            question="Tôi được nghỉ phép bao nhiêu ngày?",
            state="CLARIFICATION_REQUIRED",
        )
        session.add(original_request)
        await session.flush()

        session.add(
            MessageDB(
                id=original_user_message_id,
                conversation_id=conversation_id,
                role="USER",
                content="How many annual leave days do I receive?",
                chat_request_id=original_request_id,
            )
        )
        session.add(
            MessageDB(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                role="ASSISTANT",
                content="Are you a full-time or probationary employee?",
                chat_request_id=original_request_id,
                answer_status="CLARIFICATION_REQUIRED",
            )
        )
        await session.commit()

        history = await ChatService._load_agent_history(session, conversation_id)

    assert history == [
        {"role": "user", "content": "How many annual leave days do I receive?"},
        {"role": "assistant", "content": "Are you a full-time or probationary employee?"},
    ]


@pytest.mark.asyncio
async def test_worker_creates_ticket_for_escalation(monkeypatch):
    request_id = await create_queued_request("My salary is incorrect")
    answer = AgentAnswerDTO(
        response="HR needs to review your personal payroll data.",
        intent="out_of_scope_or_personal",
        confidence_score=None,
        escalate=True,
        escalate_reason="personal_data_required",
        ticket_draft={
            "employee_question": "My salary is incorrect",
            "escalate_reason": "personal_data_required",
            "confidence_score": None,
            "category": None,
            "target_department": "CB",
            "priority": "High",
        },
    )
    monkeypatch.setattr(
        ChatService,
        "agent_client",
        type("Client", (), {"query_agent": AsyncMock(return_value=answer)})(),
    )

    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "My salary is incorrect", CONVERSATION_ID
    )

    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        message = await session.get(MessageDB, chat_request.assistant_message_id)
        ticket = await session.get(TicketDB, message.ticket_id)
        assert chat_request.state == "REFUSED"
        assert message.escalated is True
        assert ticket.category == "GENERAL"
        assert ticket.priority == "HIGH"
        assert float(ticket.confidence_score) == 0.0


@pytest.mark.asyncio
async def test_worker_maps_agent_timeout_to_failed(monkeypatch):
    request_id = await create_queued_request("Timeout question")
    query_agent = AsyncMock(side_effect=AIAgentClientError("AGENT_TIMEOUT", "timeout"))
    monkeypatch.setattr(ChatService, "agent_client", type("Client", (), {"query_agent": query_agent})())

    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "Timeout question", CONVERSATION_ID
    )

    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        assert chat_request.state == "FAILED"
        assert chat_request.failure["code"] == "AGENT_TIMEOUT"
        assert chat_request.retryable is True
