from __future__ import annotations

from typing import Literal, TypedDict

Intent = Literal["greeting", "hr_question", "ambiguous", "out_of_scope_or_personal"]


class RetrievedChunk(TypedDict):
    chunk_id: str
    text: str
    source_file: str
    title: str
    category: str
    is_official_policy: bool
    # government_law | official_policy | public_template | synthetic |
    # public_article — cần bản đầy đủ (không chỉ cờ is_official_policy nhị phân)
    # để generate_node xếp được 3 bậc ưu tiên khi các nguồn nói khác nhau.
    source_type: str
    page_start: int | None
    page_end: int | None
    distance: float
    score: float | None


class Citation(TypedDict):
    chunk_id: str
    source_file: str
    title: str
    category: str
    page_start: int | None
    page_end: int | None
    is_official_policy: bool


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent RAG (HR Document Intelligence).

    Mỗi node đọc và ghi vào state này. total=False cho phép tất cả fields là optional.
    """

    query: str
    intent: Intent
    rewritten_query: str
    retrieved_chunks: list[RetrievedChunk]
    citations: list[Citation]
    generated_answer: str
    # False khi generate_node thấy context không chứa thông tin cụ thể được hỏi
    # (model phát ra INSUFFICIENT_MARKER). confidence_node dùng để ép điểm xuống
    # dưới ngưỡng escalate.
    answerable: bool
    confidence_score: float
    needs_clarification: bool
    clarifying_question: str
    escalate: bool
    escalate_reason: str
    ticket_category: str
    ticket_department: str
    ticket_priority: str
    rewrite_count: int
    hallucination_passed: bool
    hallucination_retry_count: int
    response: str
    error: str
    metadata: dict
