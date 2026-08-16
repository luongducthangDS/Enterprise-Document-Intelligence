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
    # Canonical runtime decision từ agent, chuyển tiếp nguyên vẹn. Backend
    # không tự suy ra action từ `state`/nội dung câu trả lời.
    boundary: dict[str, Any] | None = None
    # 'general_policy' | 'personalized' | 'not_applicable' | None — chuyển tiếp
    # nguyên vẹn từ agent, KHÔNG suy diễn lại ở backend (xem AgentAnswerDTO.answer_type).
    answer_type: str | None = None


class AgentAnswerAdapter:
    @staticmethod
    def blocks_workflow_creation(answer: AgentAnswerDTO) -> bool:
        """Lượt chat này có bị cấm sinh ra bản ghi workflow (ticket/case) không.

        MVP-1 KHÔNG có action nào tạo workflow. Trần action của MVP-1 chỉ gồm
        `NONE`, `LINK_ONLY`, `PREFILL_DRAFT`; `CREATE_CASE` là MVP-2 và luôn bị
        cap xuống `PREFILL_DRAFT` trước khi ra khỏi agent. Vì vậy hễ một lượt
        chat đi qua boundary flow thì kết quả đúng luôn là 0 ticket — bất kể
        `escalate` bằng gì.

        Trước đây hàm này chỉ chặn `HUMAN_FIRST`/`Critical`, nghĩa là các
        escalation còn lại vẫn âm thầm tạo ticket và biến ticket thành outcome
        mặc định của câu hỏi HR — đúng thứ runtime freeze cấm.

        `boundary is None` giữ nguyên hành vi cũ (tạo ticket) để không phá
        backward compatibility với agent bản cũ chưa gửi decision; đó là đường
        legacy duy nhất còn ghi ticket từ luồng chat.
        """
        return answer.boundary is not None

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
        citations_by_source: dict[str, dict[str, Any]] = {}
        for item in answer.citations:
            source_key = item.source_file.strip().casefold() or item.chunk_id
            existing = citations_by_source.get(source_key)
            if existing is not None:
                starts = [value for value in (existing["page_start"], item.page_start) if value is not None]
                ends = [value for value in (existing["page_end"], item.page_end) if value is not None]
                existing["page_start"] = min(starts) if starts else None
                existing["page_end"] = max(ends) if ends else None
                existing["page"] = existing["page_start"]
                existing["is_official_policy"] = existing["is_official_policy"] and item.is_official_policy
                continue

            citation = {
                "citation_id": cls._citation_id(chat_request_id, source_key),
                "title": item.title or item.source_file,
                "page": item.page_start,
                # Trước đây hardcode None — agent không hề gửi field này. Giờ
                # agent trả source_section (vd "4.1. Số ngày nghỉ phép năm tiêu
                # chuẩn"), client hiển thị "Nguồn: {title} · {section}".
                "section": item.source_section or None,
                "version": None,
                "effective_date": None,
                "chunk_id": item.chunk_id,
                "source_file": item.source_file,
                "page_start": item.page_start,
                "page_end": item.page_end,
                "category": item.category,
                "is_official_policy": item.is_official_policy,
                "source_type": item.source_type,
                "authority": item.authority,
                "provenance": item.provenance,
                "tenant": item.tenant,
                "policy_status": item.policy_status or None,
                "excerpt": item.excerpt,
            }
            citations_by_source[source_key] = citation
            citations.append(citation)
        return citations

    @classmethod
    def map(cls, answer: AgentAnswerDTO, chat_request_id: uuid.UUID) -> MappedAgentResult:
        citations = cls.normalize_citations(answer, chat_request_id)
        boundary = answer.boundary.model_dump() if answer.boundary else None

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
                boundary=boundary,
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
                boundary=boundary,
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
            answer_type=answer.answer_type,
            boundary=boundary,
        )
