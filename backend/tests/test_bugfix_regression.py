"""Regression tests cho các bug đã remediate ngày 2026-08-22.

BUG-01: AgentAnswerDTO từ chối intent pure_statutory → statutory query bị
        AGENT_INVALID_RESPONSE. Fix: thêm Literal + adapter map REFUSED.
BUG-03: Re-upload cùng (tenant, source_file) → 500 UniqueViolation.
        Fix: ConflictError 409 DOCUMENT_ALREADY_EXISTS.
"""

import io
import uuid

import pytest_asyncio
from app.core.security import hash_password
from app.domain.models.profile import ProfileDB
from app.domain.models.user import UserDB
from app.schemas.agent import AgentAnswerDTO
from app.services.agent_answer_adapter import AgentAnswerAdapter
from tests.conftest import TestingSessionLocal, client
from tests.test_documents import get_auth_header


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_bugfix_test_data():
    """auth_deps reload identity từ ProfileDB — phải seed user admin test."""
    async with TestingSessionLocal() as session:
        admin_id = uuid.UUID("88888888-8888-8888-8888-888888888888")
        admin = await session.get(UserDB, admin_id)
        if not admin:
            admin = UserDB(
                id=admin_id,
                email="doc_admin@company.com",
                hashed_password=hash_password("password123"),
            )
            admin.profile = ProfileDB(
                id=admin_id,
                display_name="Doc Admin",
                role="DEPARTMENT_MANAGER",
                department="HR",
            )
            session.add(admin)
        await session.commit()


# ---------------------------------------------------------------- BUG-01
def test_agent_answer_dto_accepts_pure_statutory():
    payload = {
        "response": "Câu hỏi thuộc phạm vi quy định pháp luật nhà nước, ngoài phạm vi chính sách nội bộ.",
        "intent": "pure_statutory",
        "confidence_score": None,
        "citations": [],
        "escalate": False,
        "escalate_reason": None,
    }
    dto = AgentAnswerDTO(**payload)
    assert dto.intent == "pure_statutory"


def test_adapter_maps_pure_statutory_to_refused_non_retryable():
    dto = AgentAnswerDTO(
        response="Từ chối theo contract Type C.",
        intent="pure_statutory",
    )
    mapped = AgentAnswerAdapter.map(dto, uuid.uuid4())
    assert mapped.state == "REFUSED"
    assert mapped.retryable is False
    assert mapped.message_content == "Từ chối theo contract Type C."


def test_adapter_out_of_scope_personal_still_refused_retryable():
    dto = AgentAnswerDTO(
        response="Cần chuyển HR xử lý.",
        intent="out_of_scope_or_personal",
    )
    mapped = AgentAnswerAdapter.map(dto, uuid.uuid4())
    assert mapped.state == "REFUSED"
    assert mapped.retryable is True


# ---------------------------------------------------------------- BUG-03
def test_duplicate_upload_returns_409_conflict():
    headers = get_auth_header()
    fname = f"dup_regression_{uuid.uuid4().hex[:6]}.pdf"
    files = {"file": (fname, io.BytesIO(b"%PDF-1.4 regression"), "application/pdf")}

    first = client.post("/api/v1/documents", headers=headers, files=files, data={"department": "HR"})
    assert first.status_code == 201

    # Upload lần 2 cùng filename + tenant → phải 409 DOCUMENT_ALREADY_EXISTS
    files2 = {"file": (fname, io.BytesIO(b"%PDF-1.4 regression again"), "application/pdf")}
    second = client.post("/api/v1/documents", headers=headers, files=files2, data={"department": "HR"})
    assert second.status_code == 409
    body = second.json()
    assert body["error"]["code"] == "DOCUMENT_ALREADY_EXISTS"
    # Không lộ raw DB exception
    assert "UniqueViolation" not in body["error"]["message"]
    assert "duplicate key" not in body["error"]["message"]
