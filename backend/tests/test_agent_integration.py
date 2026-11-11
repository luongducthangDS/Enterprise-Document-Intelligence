import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
from app.schemas.agent import AgentAnswerDTO, AgentCitationDTO
from app.services.agent_answer_adapter import AgentAnswerAdapter
from app.services.ai_agent_client import AIAgentClientError
from app.services.chat_service import ChatService
from sqlalchemy import func, select

from tests.conftest import TestingSessionLocal

# Registry canonical nằm ở repo root; backend image chỉ COPY thư mục backend/
# nên test đọc file này phải skip khi chạy trong container.
SCENARIO_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "src" / "agents" / "resources" / "scenario_registry.json"

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
                "document_code": "HR-LEAVE-01",
                "version": "2.1",
                "effective_date": "2026-01-01",
                "excerpt": "Employees receive 12 leave days per year.",
            }
        ],
    )


def test_adapter_generates_stable_citation_ids():
    request_id = uuid.uuid4()
    first = AgentAnswerAdapter.map(normal_answer(), request_id)
    second = AgentAnswerAdapter.map(normal_answer(), request_id)
    assert first.citations[0]["citation_id"] == second.citations[0]["citation_id"]
    assert first.citations[0]["page"] == 2
    assert first.citations[0]["excerpt"] == "Employees receive 12 leave days per year."
    assert first.citations[0]["document_code"] == "HR-LEAVE-01"
    assert first.citations[0]["version"] == "2.1"
    assert first.citations[0]["effective_date"] == "2026-01-01"


def test_adapter_groups_chunks_from_the_same_document():
    answer = normal_answer()
    answer.citations.append(
        AgentCitationDTO(
            chunk_id="leave-policy::0002",
            source_file="leave-policy.pdf",
            title="Leave Policy",
            page_start=4,
            page_end=5,
            category="leave",
            is_official_policy=True,
        )
    )

    result = AgentAnswerAdapter.map(answer, uuid.uuid4())

    assert len(result.citations) == 1
    assert result.citations[0]["page_start"] == 2
    assert result.citations[0]["page_end"] == 5


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
        assert chat_request.citations[0]["excerpt"] == "Employees receive 12 leave days per year."
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

        now = datetime.now(UTC)
        session.add(
            MessageDB(
                id=original_user_message_id,
                conversation_id=conversation_id,
                role="user",
                content="How many annual leave days do I receive?",
                chat_request_id=original_request_id,
                created_at=now,
            )
        )
        session.add(
            MessageDB(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                role="assistant",
                content="Are you a full-time or probationary employee?",
                chat_request_id=original_request_id,
                created_at=now + timedelta(seconds=1),
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
        assert ticket.priority == "High"
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


HUMAN_FIRST_BOUNDARY = {
    "scenario_id": 52,
    "scenario_name": "Harassment/discrimination concern",
    "service_code": "EMPLOYEE_RELATIONS",
    "service_name": "Quan hệ lao động",
    "assistant_role": "HUMAN_FIRST",
    "sensitivity": "Critical",
    "runtime_source_status": "HUMAN",
    "source_of_truth_label": "Người phụ trách",
    "max_runtime_action": "LINK_ONLY",
    "runtime_action": "LINK_ONLY",
    "mvp_phase": "FUTURE",
    "handoff_target": {"type": "department", "code": "ER", "name": "ER", "contact_label": "Bộ phận Employee Relations"},
    "user_facing_action_label": "Hướng dẫn gửi",
    "allowed_data_fields": [
        {
            "field_key": "urgency_level",
            "label": "Mức khẩn cấp",
            "required_for_prefill": False,
            "pii_class": "High",
            "storage_policy": "store_case_only",
        }
    ],
    "runtime_behavior": "Hướng dẫn hotline/ER, không lấy lời khai chi tiết.",
    "resolution": "registry",
}


def test_adapter_passes_boundary_decision_through_unchanged():
    answer = AgentAnswerDTO(
        response="Bạn liên hệ bộ phận Employee Relations nhé.",
        intent="hr_question",
        boundary=HUMAN_FIRST_BOUNDARY,
    )
    mapped = AgentAnswerAdapter.map(answer, uuid.uuid4())
    assert mapped.boundary["scenario_id"] == 52
    assert mapped.boundary["runtime_action"] == "LINK_ONLY"
    assert mapped.boundary["max_runtime_action"] == "LINK_ONLY"


def test_adapter_keeps_boundary_null_for_legacy_agent_payload():
    answer = AgentAnswerDTO(response="Câu trả lời", intent="hr_question")
    assert AgentAnswerAdapter.map(answer, uuid.uuid4()).boundary is None


def test_adapter_blocks_workflow_creation_for_every_boundary_decision():
    """MVP-1 không có action nào tạo workflow, kể cả nhánh hành chính ít nhạy cảm."""
    for role in ("ANSWER", "GUIDE", "PREPARE_AND_HANDOFF", "HUMAN_FIRST"):
        for action in ("NONE", "LINK_ONLY", "PREFILL_DRAFT"):
            for sensitivity in ("Low", "Medium", "High", "Critical"):
                answer = AgentAnswerDTO(
                    response="x",
                    intent="hr_question",
                    boundary={
                        **HUMAN_FIRST_BOUNDARY,
                        "assistant_role": role,
                        "runtime_action": action,
                        "sensitivity": sensitivity,
                    },
                )
                assert AgentAnswerAdapter.blocks_workflow_creation(answer) is True, (role, action, sensitivity)


def test_adapter_keeps_legacy_ticket_path_when_agent_sends_no_boundary():
    """Backward compatibility: agent bản cũ chưa gửi decision vẫn đi đường cũ."""
    assert AgentAnswerAdapter.blocks_workflow_creation(AgentAnswerDTO(response="x", intent="hr_question")) is False


@pytest.mark.skipif(not SCENARIO_REGISTRY_PATH.exists(), reason="canonical registry chỉ có ở repo, không có trong image backend")
def test_no_mvp1_scenario_can_produce_a_workflow_record():
    """Duyệt ĐÚNG registry canonical: 0/64 scenario được phép tạo ticket ở MVP-1."""
    registry = json.loads(SCENARIO_REGISTRY_PATH.read_text(encoding="utf-8"))
    ceiling = registry["mvp1_capability_ceiling"]
    checked = 0
    for scenario in registry["scenarios"]:
        max_action = scenario["max_runtime_action"]
        runtime_action = max_action if max_action in ceiling else ceiling[-1]
        answer = AgentAnswerDTO(
            response="x",
            intent="hr_question",
            boundary={
                **HUMAN_FIRST_BOUNDARY,
                "scenario_id": scenario["id"],
                "scenario_name": scenario["name"],
                "assistant_role": scenario["assistant_role"],
                "sensitivity": scenario["sensitivity"],
                "max_runtime_action": max_action,
                "runtime_action": runtime_action,
                "mvp_phase": scenario["mvp_phase"],
            },
        )
        assert runtime_action != "CREATE_CASE", scenario["id"]
        assert AgentAnswerAdapter.blocks_workflow_creation(answer) is True, scenario["id"]
        checked += 1
    assert checked == 64


@pytest.mark.asyncio
async def test_worker_does_not_create_ticket_when_boundary_is_human_first(monkeypatch):
    request_id = await create_queued_request("Tôi bị quấy rối ở công ty")
    answer = AgentAnswerDTO(
        response="Nội dung này cần trao đổi trực tiếp với người có thẩm quyền.",
        intent="out_of_scope_or_personal",
        escalate=True,
        escalate_reason="personal_data_required",
        ticket_draft={
            "employee_question": "Tôi bị quấy rối ở công ty",
            "escalate_reason": "personal_data_required",
            "confidence_score": None,
            "category": None,
            "target_department": "ER",
            "priority": "High",
        },
        boundary=HUMAN_FIRST_BOUNDARY,
    )
    monkeypatch.setattr(
        ChatService,
        "agent_client",
        type("Client", (), {"query_agent": AsyncMock(return_value=answer)})(),
    )

    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "Tôi bị quấy rối ở công ty", CONVERSATION_ID
    )

    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        message = await session.get(MessageDB, chat_request.assistant_message_id)
        assert chat_request.state == "REFUSED"
        assert message.ticket_id is None


@pytest.mark.asyncio
async def test_worker_creates_no_ticket_for_routine_boundary_escalation(monkeypatch):
    """Nhánh escalate thường (không nhạy cảm) cũng không được sinh ticket.

    Đây là ca hồi quy chính của corrective pass: trước đó chỉ HUMAN_FIRST/Critical
    bị chặn, nên một câu hỏi chấm công đi vào nhánh escalate vẫn tạo ticket và
    biến ticket thành outcome mặc định.
    """
    request_id = await create_queued_request("Quên chấm công hôm qua")
    answer = AgentAnswerDTO(
        response="Mình đã chuẩn bị nội dung yêu cầu để bạn chuyển tới người phụ trách.",
        intent="out_of_scope_or_personal",
        escalate=True,
        escalate_reason="personal_data_required",
        ticket_draft={
            "employee_question": "Quên chấm công hôm qua",
            "escalate_reason": "personal_data_required",
            "confidence_score": None,
            "category": None,
            "target_department": "HRBP",
            "priority": "Medium",
        },
        boundary={
            **HUMAN_FIRST_BOUNDARY,
            "scenario_id": 11,
            "scenario_name": "Quên chấm công",
            "assistant_role": "GUIDE",
            "sensitivity": "Low",
            "max_runtime_action": "PREFILL_DRAFT",
            "runtime_action": "PREFILL_DRAFT",
            "mvp_phase": "MVP_1",
        },
    )
    monkeypatch.setattr(
        ChatService,
        "agent_client",
        type("Client", (), {"query_agent": AsyncMock(return_value=answer)})(),
    )

    async with TestingSessionLocal() as session:
        tickets_before = await session.scalar(select(func.count(TicketDB.id)))

    await ChatService._process_chat_rag_request(
        request_id, USER_ID, "Engineering", "Quên chấm công hôm qua", CONVERSATION_ID
    )

    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        message = await session.get(MessageDB, chat_request.assistant_message_id)
        tickets_after = await session.scalar(select(func.count(TicketDB.id)))
        assert chat_request.state == "REFUSED"
        assert message.ticket_id is None
        assert tickets_after == tickets_before
        # Invariant ngữ nghĩa: escalated=True nghĩa là "cần người xử lý", KHÔNG
        # phải "đã tạo ticket". Cặp (escalated=True, ticket_id=None) là trạng
        # thái hợp lệ của boundary flow và không được coi là bug.
        assert message.escalated is True


def _create_case_answer(question: str, **boundary_overrides) -> AgentAnswerDTO:
    return AgentAnswerDTO(
        response="Mình đã chuẩn bị nội dung yêu cầu để bạn gửi tới bộ phận phụ trách.",
        intent="out_of_scope_or_personal",
        escalate=True,
        escalate_reason="personal_data_required",
        ticket_draft={
            "employee_question": question,
            "escalate_reason": "personal_data_required",
            "confidence_score": None,
            "category": "PAYROLL",
            "target_department": "CB",
            "priority": "High",
        },
        boundary={
            **HUMAN_FIRST_BOUNDARY,
            "scenario_id": 21,
            "scenario_name": "Payroll discrepancy",
            "assistant_role": "PREPARE_AND_HANDOFF",
            "sensitivity": "High",
            "max_runtime_action": "CREATE_CASE",
            "runtime_action": "PREFILL_DRAFT",
            "mvp_phase": "MVP_2",
            **boundary_overrides,
        },
    )


async def _run_with_answer(monkeypatch, question: str, answer: AgentAnswerDTO) -> uuid.UUID:
    request_id = await create_queued_request(question)
    monkeypatch.setattr(
        ChatService, "agent_client", type("Client", (), {"query_agent": AsyncMock(return_value=answer)})()
    )
    await ChatService._process_chat_rag_request(request_id, USER_ID, "Engineering", question, CONVERSATION_ID)
    return request_id


@pytest.mark.asyncio
async def test_create_case_needs_user_confirmation_and_is_idempotent(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "enable_create_case", True)
    q = "Lương tháng này bị trừ sai"
    request_id = await _run_with_answer(monkeypatch, q, _create_case_answer(q))

    async with TestingSessionLocal() as session:
        before = await session.scalar(select(func.count(TicketDB.id)))
        chat_request = await session.get(ChatRequestDB, request_id)
        # Agent chỉ đề xuất: chưa có ticket nào cho tới khi người hỏi xác nhận.
        assert chat_request.ticket_proposal["status"] == "PENDING"
        assert ChatService._status_payload(chat_request)["ticket_proposal"]["status"] == "PENDING"

    async with TestingSessionLocal() as session:
        first = await ChatService.confirm_ticket_proposal(session, request_id, USER_ID)
    async with TestingSessionLocal() as session:
        second = await ChatService.confirm_ticket_proposal(session, request_id, USER_ID)
        after = await session.scalar(select(func.count(TicketDB.id)))
        chat_request = await session.get(ChatRequestDB, request_id)
        message = await session.get(MessageDB, chat_request.assistant_message_id)

    assert first["status"] == "CONFIRMED" and first["ticket_id"] == second["ticket_id"]
    assert after == before + 1
    assert str(message.ticket_id) == first["ticket_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,overrides",
    [
        (False, {}),  # cờ tắt = MVP-1
        (True, {"max_runtime_action": "PREFILL_DRAFT"}),  # registry không cho CREATE_CASE
        (True, {"sensitivity": "Critical"}),
        (True, {"assistant_role": "HUMAN_FIRST"}),
    ],
)
async def test_no_case_proposal_outside_create_case_gate(monkeypatch, enabled, overrides):
    from app.core.config import get_settings
    from app.core.exceptions import ConflictError, ForbiddenError

    monkeypatch.setattr(get_settings(), "enable_create_case", enabled)
    q = "Lương tháng này bị trừ sai"
    request_id = await _run_with_answer(monkeypatch, q, _create_case_answer(q, **overrides))
    async with TestingSessionLocal() as session:
        chat_request = await session.get(ChatRequestDB, request_id)
        assert chat_request.ticket_proposal is None
        with pytest.raises((ConflictError, ForbiddenError)):
            await ChatService.confirm_ticket_proposal(session, request_id, USER_ID)


@pytest.mark.asyncio
async def test_only_requester_can_confirm(monkeypatch):
    from app.core.config import get_settings
    from app.core.exceptions import ForbiddenError

    monkeypatch.setattr(get_settings(), "enable_create_case", True)
    q = "Lương tháng này bị trừ sai"
    request_id = await _run_with_answer(monkeypatch, q, _create_case_answer(q))
    async with TestingSessionLocal() as session:
        with pytest.raises(ForbiddenError):
            await ChatService.confirm_ticket_proposal(session, request_id, uuid.uuid4())


@pytest.mark.asyncio
async def test_reject_case_proposal_blocks_confirm_and_is_audited(monkeypatch):
    from app.core.config import get_settings
    from app.core.exceptions import ConflictError
    from app.domain.models.audit import AuditLogDB

    monkeypatch.setattr(get_settings(), "enable_create_case", True)
    q = "Lương tháng này bị trừ sai"
    request_id = await _run_with_answer(monkeypatch, q, _create_case_answer(q))
    async with TestingSessionLocal() as session:
        before = await session.scalar(select(func.count(TicketDB.id)))
    async with TestingSessionLocal() as session:
        first = await ChatService.reject_ticket_proposal(session, request_id, USER_ID, "Tôi tự xử lý được")
    async with TestingSessionLocal() as session:
        again = await ChatService.reject_ticket_proposal(session, request_id, USER_ID, "lý do khác")
    async with TestingSessionLocal() as session:
        with pytest.raises(ConflictError):
            await ChatService.confirm_ticket_proposal(session, request_id, USER_ID)
        after = await session.scalar(select(func.count(TicketDB.id)))
        audits = (await session.execute(
            select(AuditLogDB).where(AuditLogDB.resource_id == str(request_id))
        )).scalars().all()

    assert first["status"] == "REJECTED" and first["rejection_reason"] == "Tôi tự xử lý được"
    assert again["rejection_reason"] == "Tôi tự xử lý được"  # idempotent, không ghi đè
    assert after == before
    assert [a.action for a in audits] == ["AGENT_CASE_REJECTED"]
    assert audits[0].before_state["status"] == "PENDING" and audits[0].actor_id == USER_ID


@pytest.mark.asyncio
async def test_confirm_writes_audit_and_blocks_later_reject(monkeypatch):
    from app.core.config import get_settings
    from app.core.exceptions import ConflictError
    from app.domain.models.audit import AuditLogDB

    monkeypatch.setattr(get_settings(), "enable_create_case", True)
    q = "Lương tháng này bị trừ sai"
    request_id = await _run_with_answer(monkeypatch, q, _create_case_answer(q))
    async with TestingSessionLocal() as session:
        confirmed = await ChatService.confirm_ticket_proposal(session, request_id, USER_ID)
    async with TestingSessionLocal() as session:
        with pytest.raises(ConflictError):
            await ChatService.reject_ticket_proposal(session, request_id, USER_ID)
        audit = (await session.execute(
            select(AuditLogDB).where(AuditLogDB.resource_id == str(request_id))
        )).scalar_one()
    assert audit.action == "AGENT_CASE_CONFIRMED"
    assert audit.after_state == {"status": "CONFIRMED", "ticket_code": confirmed["ticket_code"], "rejection_reason": None}
