from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")


Role = Literal["employee", "manager", "hr_admin"]
EmploymentStatus = Literal["probation", "full_time", "on_notice_termination", "resigned"]
ContractType = Literal["xac_dinh_thoi_han", "khong_xac_dinh_thoi_han", "thu_viec"]
AccessLevel = Literal["self_only", "team_scope", "org_wide"]
EscalateReason = Literal["low_confidence", "out_of_scope", "personal_data_required", "user_requested_human"]
TargetDepartment = Literal["CB", "ER", "TA", "LD", "HRBP"]
TicketPriority = Literal["Low", "Medium", "High"]
TicketStatus = Literal["open", "in_progress", "resolved", "closed"]
DocumentStatus = Literal["raw", "processed", "processed_incomplete", "rejected"]
DocumentSourceType = Literal[
    "government_law",
    "official_policy",
    "public_template",
    "synthetic",
    "public_article",
    "eval_asset",
    "config",
    "rejected",
]


class Profile(BaseModel):
    id: UUID = Field(..., description="Khớp auth.users.id")
    display_name: str = Field(..., description="Tên hiển thị")
    role: Role = Field(..., description="Vai trò: employee / manager / hr_admin")
    employment_status: EmploymentStatus = Field(default="full_time", description="Trạng thái hợp đồng")
    department: Optional[str] = Field(default=None, description="Phòng ban")
    business_unit: Optional[str] = Field(default=None, description="Khối/đơn vị kinh doanh")
    contract_type: Optional[ContractType] = Field(default=None, description="Loại hợp đồng lao động")
    tenure_months: int = Field(default=0, description="Số tháng làm việc")
    seniority_years: int = Field(default=0, description="Số năm thâm niên")
    access_level: AccessLevel = Field(default="self_only", description="Phạm vi truy cập dữ liệu")
    manager_id: Optional[UUID] = Field(default=None, description="ID quản lý trực tiếp (cho team_scope)")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Conversation(BaseModel):
    id: UUID
    user_id: UUID
    title: Optional[str] = Field(default=None, description="Tiêu đề hội thoại")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Citation(BaseModel):
    chunk_id: str
    source_file: str
    title: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    category: str
    is_official_policy: bool


class Message(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(..., description="Nội dung tin nhắn")
    citations: list[Citation] = Field(default_factory=list, description="Trích dẫn nguồn (chỉ có ở tin nhắn assistant)")
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Độ tin cậy câu trả lời")
    escalated: bool = Field(default=False, description="Có bị escalate sang ticket không")
    ticket_id: Optional[UUID] = None
    created_at: Optional[datetime] = None


class TicketRequester(BaseModel):
    user_id: UUID
    role: Role
    department: Optional[str] = None


class Ticket(BaseModel):
    id: UUID
    ticket_code: str = Field(..., description="Mã ticket, vd TCK-2026-000123")
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    requester_id: UUID
    employee_question: str = Field(..., description="Câu hỏi gốc của nhân viên")
    escalate_reason: EscalateReason
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    category: Optional[str] = None
    target_department: TargetDepartment = Field(..., description="Phòng ban xử lý: C&B/ER/TA/L&D/HRBP")
    priority: TicketPriority
    status: TicketStatus = Field(default="open")
    assignee_id: Optional[UUID] = Field(default=None, description="HR admin được gán xử lý")
    resolution_note: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class Document(BaseModel):
    id: UUID
    source_file: str
    category: str
    status: DocumentStatus = Field(default="raw")
    source_type: DocumentSourceType
    is_official_policy: bool = Field(..., description="False nếu là template công khai/synthetic — KHÔNG phải chính sách công ty thật")
    caveat: Optional[str] = Field(default=None, description="Cảnh báo/lưu ý khi trích dẫn tài liệu này")
    processed_path: Optional[str] = None
    chunks_path: Optional[str] = None
    chroma_indexed_at: Optional[datetime] = Field(default=None, description="Thời điểm index vào Chroma Cloud")
    uploaded_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
