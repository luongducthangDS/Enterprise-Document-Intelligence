import uuid
from dataclasses import dataclass
from typing import Any

from app.schemas.agent import AgentAnswerDTO


@dataclass(frozen=True)
class MappedAgentResult:
    state: str
    answer_status: str
    answer: str | None
    message_content: str
    citations: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    clarification: dict[str, Any] | None
    retryable: bool


class AgentAnswerAdapter:
    @staticmethod
    def _citation_id(chat_request_id: uuid.UUID, chunk_id: str) -> str:
        value = uuid.uuid5(uuid.NAMESPACE_URL, f"{chat_request_id}:{chunk_id}")
        return f"cit_{value.hex}"

    @classmethod
    def normalize_citations(
        cls,
        answer: AgentAnswerDTO,
        chat_request_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for item in answer.citations:
            citations.append(
                {
                    "citation_id": cls._citation_id(chat_request_id, item.chunk_id),
                    "title": item.title or item.source_file,
                    "page": item.page_start,
                    "section": None,
                    "version": None,
                    "effective_date": None,
                    "chunk_id": item.chunk_id,
                    "source_file": item.source_file,
                    "page_start": item.page_start,
                    "page_end": item.page_end,
                    "category": item.category,
                    "is_official_policy": item.is_official_policy,
                    "source_type": item.source_type,
                    "excerpt": item.excerpt,
                }
            )
        return citations

    @classmethod
    def map(cls, answer: AgentAnswerDTO, chat_request_id: uuid.UUID) -> MappedAgentResult:
        citations = cls.normalize_citations(answer, chat_request_id)

        if answer.needs_clarification:
            question = (answer.clarifying_question or answer.response).strip()
            return MappedAgentResult(
                state="CLARIFICATION_REQUIRED",
                answer_status="CLARIFICATION_REQUIRED",
                answer=None,
                message_content=question,
                citations=[],
                warnings=[],
                clarification={"question": question, "options": []},
                retryable=False,
            )

        if answer.escalate or answer.intent == "out_of_scope_or_personal":
            warnings = []
            if answer.escalate_reason == "low_confidence":
                warnings.append(
                    {
                        "type": "INCOMPLETE_DATA",
                        "severity": "BLOCKING",
                        "message": "Không đủ bằng chứng để trả lời một cách tin cậy.",
                        "citation_ids": [item["citation_id"] for item in citations] or None,
                        "recommended_action": "Liên hệ HR để được hỗ trợ.",
                    }
                )
            return MappedAgentResult(
                state="REFUSED",
                answer_status="INSUFFICIENT_EVIDENCE",
                answer=answer.response,
                message_content=answer.response,
                citations=citations,
                warnings=warnings,
                clarification=None,
                retryable=True,
            )

        return MappedAgentResult(
            state="COMPLETED",
            answer_status="ANSWERED",
            answer=answer.response,
            message_content=answer.response,
            citations=citations,
            warnings=[],
            clarification=None,
            retryable=False,
        )
