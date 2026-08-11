import uuid

from app.schemas.agent import AgentAnswerDTO
from app.services.agent_answer_adapter import AgentAnswerAdapter
from app.services.content_safety import redact_pii, sanitize_citations_for_client


def test_redact_pii_covers_email_phone_and_cccd():
    value = "hr@company.com 0912345678 012345678901"

    redacted = redact_pii(value)

    assert "hr@company.com" not in redacted
    assert "0912345678" not in redacted
    assert "012345678901" not in redacted


def test_client_sanitizer_redacts_pii_without_changing_persisted_citation():
    answer = AgentAnswerDTO(
        response="Safe answer",
        intent="hr_question",
        citations=[
            {
                "chunk_id": "policy::1",
                "source_file": "owner-hr@company.com.pdf",
                "title": "Contact 0912345678",
                "category": "leave",
                "is_official_policy": True,
            }
        ],
    )

    citation = AgentAnswerAdapter.map(answer, uuid.uuid4()).citations[0]
    sanitized = sanitize_citations_for_client([citation])[0]

    assert "hr@company.com" in citation["source_file"]
    assert "hr@company.com" not in sanitized["source_file"]
    assert "0912345678" not in sanitized["title"]
