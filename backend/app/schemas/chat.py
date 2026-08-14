from typing import Any

from pydantic import BaseModel, Field


class CreateChatRequestSchema(BaseModel):
    conversation_id: str = Field(..., description="ID phiên hội thoại")
    question: str = Field(
        ...,
        min_length=1,
        description="Câu hỏi của người dùng",
    )


class ChatRequestCreatedDTO(BaseModel):
    chat_request_id: str
    conversation_id: str
    state: str = "QUEUED"
    poll_after_ms: int = 1000


class RetryChatRequestSchema(BaseModel):
    reason: str | None = Field(default="USER_RETRY", description="Lý do thử lại")


class ChatRequestRetryCreatedDTO(BaseModel):
    chat_request_id: str
    parent_chat_request_id: str
    state: str = "QUEUED"
    poll_after_ms: int = 1000


class WarningDTO(BaseModel):
    type: str  # INCOMPLETE_DATA, CONFLICTING_SOURCES, UNCLEAR_SOURCE, OUTDATED_OR_SUPERSEDED_SOURCE
    severity: str  # INFO, WARNING, BLOCKING
    message: str
    citation_ids: list[str] | None = None
    recommended_action: str | None = None


class ClarificationDTO(BaseModel):
    question: str
    options: list[str]


class FailureDTO(BaseModel):
    code: str
    message: str
    retryable: bool = True


class ChatRequestStatusDTO(BaseModel):
    chat_request_id: str
    conversation_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    state: str  # QUEUED, RETRIEVING, GENERATING, COMPLETED, REFUSED, CLARIFICATION_REQUIRED, FAILED
    answer_status: str | None = None  # ANSWERED, INSUFFICIENT_EVIDENCE, CLARIFICATION_REQUIRED
    answer: str | None = None
    citations: list[dict[str, Any]] | None = None
    warnings: list[WarningDTO] | None = None
    clarification: ClarificationDTO | None = None
    failure: FailureDTO | None = None
    latency_ms: int | None = None
