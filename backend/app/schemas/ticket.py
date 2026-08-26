import uuid

from pydantic import BaseModel, ConfigDict, Field


class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    employee_question: str = Field(..., alias="user_query", description="Câu hỏi / Yêu cầu của nhân viên")
    escalate_reason: str = Field("user_requested_human", description="Lý do chuyển tiếp ticket")
    target_department: str = Field("HRBP", description="Phòng ban tiếp nhận (CB, ER, TA, LD, HRBP, HR, ACCOUNTING, PRODUCT)")
    priority: str = Field("Medium", description="Mức độ ưu tiên (Low, Medium, High)")
    category: str | None = Field("GENERAL", description="Phân loại chủ đề")
    confidence_score: float | None = Field(None, ge=0.0, le=1.0, description="Điểm độ tin cậy RAG")
    conversation_id: uuid.UUID | None = Field(None, description="ID cuộc hội thoại liên quan")
    message_id: uuid.UUID | None = Field(None, description="ID tin nhắn liên quan")


class TicketUpdateRequest(BaseModel):
    status: str | None = Field(None, description="Trạng thái ticket (open, in_progress, resolved, closed)")
    assignee_id: uuid.UUID | None = Field(None, description="ID người xử lý (HR Admin)")
    resolution_note: str | None = Field(None, description="Ghi chú giải quyết ticket")
    priority: str | None = Field(None, description="Mức độ ưu tiên (Low, Medium, High)")


class TicketResponseDTO(BaseModel):
    id: str
    ticket_code: str
    conversation_id: str | None = None
    message_id: str | None = None
    requester_id: str
    requester_name: str | None = None
    employee_question: str
    escalate_reason: str
    confidence_score: float | None = None
    category: str | None = None
    target_department: str
    priority: str
    status: str
    assignee_id: str | None = None
    assignee_name: str | None = None
    resolution_note: str | None = None
    created_at: str
    updated_at: str
    resolved_at: str | None = None
    closed_at: str | None = None
