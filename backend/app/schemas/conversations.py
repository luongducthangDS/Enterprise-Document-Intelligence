from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, description="Tiêu đề cuộc hội thoại (tùy chọn)")


class ConversationResponseDTO(BaseModel):
    conversation_id: str
    title: str
    state: str
    created_at: str
    ended_at: str | None = None
    message_count: int = 0
    last_message_at: str | None = None


class CitationDTO(BaseModel):
    citation_id: str
    title: str
    page: int | None = None
    section: str | None = None
    version: str | None = None
    effective_date: str | None = None


class MessageDTO(BaseModel):
    message_id: str
    role: str
    content: str
    chat_request_id: str | None = None
    answer_status: str | None = None
    citations: list[CitationDTO] | list[dict[str, Any]] | None = None
    created_at: str


class MessagesListDTO(BaseModel):
    conversation_id: str
    messages: list[MessageDTO]
    pagination: dict[str, Any]


class EndConversationDTO(BaseModel):
    conversation_id: str
    state: str = "ENDED"
    ended_at: str
