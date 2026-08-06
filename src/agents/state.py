from __future__ import annotations

from typing import Literal, Optional, TypedDict

Intent = Literal["greeting", "hr_question", "ambiguous", "out_of_scope_or_personal"]


class RetrievedChunk(TypedDict):
    chunk_id: str
    text: str
    source_file: str
    title: str
    category: str
    is_official_policy: bool
    page_start: Optional[int]
    page_end: Optional[int]
    distance: float


class Citation(TypedDict):
    chunk_id: str
    source_file: str
    title: str
    page_start: Optional[int]
    page_end: Optional[int]
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
