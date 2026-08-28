from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, description="Tiêu đề cuộc hội thoại (tùy chọn)")


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120, description="Tiêu đề mới của cuộc hội thoại")


class ConversationResponseDTO(BaseModel):
    conversation_id: str
    title: str
    state: str
    created_at: str
    updated_at: str | None = None
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
    is_official_policy: bool = Field(
        default=True, description="Xác định tài liệu chính sách chính thức hay không"
    )
    source_type: str | None = Field(default=None, description="Loại nguồn tài liệu")
    public_url: str | None = Field(default=None, description="Public URL mở tài liệu trực tiếp")
    document_id: str | None = Field(default=None, description="ID tài liệu trong DB")
    chunk_id: str | None = Field(default=None, description="ID chunk trích dẫn")
    excerpt: str | None = Field(default=None, description="Đoạn trích dẫn")


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
