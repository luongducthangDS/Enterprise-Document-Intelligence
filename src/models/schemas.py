from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.agents.state import Intent


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=5000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    history: list[HistoryTurn] = Field(
        default_factory=list, description="Các lượt hội thoại trước đó (cũ -> mới), rỗng nếu là lượt đầu"
    )


class AgentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1, max_length=128)
    user_id: str = Field(..., min_length=1, max_length=128)
    department: str = Field(default="GENERAL", max_length=128)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=16)


class IngestionJobRequest(BaseModel):
    """Backend giao 1 tài liệu cho agent parse -> chunk -> embed -> index.

    `job_id` do Backend cấp và là khoá idempotent: submit lại cùng job_id khi job
    chưa kết thúc sẽ bị từ chối 409.
    """

    job_id: str = Field(..., min_length=1, max_length=128)
    document_id: str | None = Field(default=None, max_length=128, description="ID tài liệu bên Backend, để trace")
    source_file: str = Field(
        ..., min_length=1, max_length=255, description="Tên file gốc — quyết định chunk_id/source_stem"
    )
    content_base64: str = Field(..., min_length=1, description="Nội dung file, base64")
    category: str = Field(default="GENERAL", max_length=64)
    source_type: str = Field(default="official_policy", max_length=64)
    is_official_policy: bool = True
    caveat: str = Field(default="", max_length=500)


class IndexRebuildTarget(BaseModel):
    document_id: str | None = Field(default=None, max_length=128)
    source_file: str = Field(..., min_length=1, max_length=255)


class IndexRebuildJobRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    documents: list[IndexRebuildTarget] = Field(
        default_factory=list, description="Rỗng = rebuild toàn bộ tài liệu đã có chunk"
    )
    strategy: Literal["REPLACE", "INCREMENTAL", "FULL"] = "REPLACE"


class EvaluationJobRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    dataset_id: str = Field(default="evalset_hr_v1", max_length=128)
    limit: int | None = Field(default=None, ge=1, le=1000, description="Chỉ chạy N câu đầu (smoke run)")
    concurrency: int | None = Field(default=None, ge=1, le=16)
    types: list[str] | None = Field(default=None, description="Lọc theo type câu hỏi, vd ['in_scope']")


class JobAcceptedResponse(BaseModel):
    job_id: str
    kind: str
    state: str = "QUEUED"
    poll_after_ms: int = 2000


class JobStatusResponse(BaseModel):
    job_id: str
    kind: str
    state: Literal["QUEUED", "PROCESSING", "COMPLETED", "FAILED"]
    stage: str
    progress_percent: int
    result: dict | None = None
    error: str | None = None
    poll_after_ms: int = 2000


Role = Literal["employee", "manager", "hr_admin"]
EmploymentStatus = Literal["probation", "full_time", "on_notice_termination", "resigned"]
ContractType = Literal["xac_dinh_thoi_han", "khong_xac_dinh_thoi_han", "thu_viec"]
AccessLevel = Literal["self_only", "team_scope", "org_wide"]
# "competitor_question" không tạo ticket (escalate=False) — xem escalate_node
# trong src/agents/nodes/escalation.py — nhưng vẫn cần xuất hiện trong Literal
# này vì AgentAnswer.escalate_reason phản ánh giá trị thật agent trả về.
EscalateReason = Literal[
    "low_confidence", "out_of_scope", "personal_data_required", "user_requested_human", "competitor_question"
]
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
    department: str | None = Field(default=None, description="Phòng ban")
    business_unit: str | None = Field(default=None, description="Khối/đơn vị kinh doanh")
    contract_type: ContractType | None = Field(default=None, description="Loại hợp đồng lao động")
    tenure_months: int = Field(default=0, description="Số tháng làm việc")
    seniority_years: int = Field(default=0, description="Số năm thâm niên")
    access_level: AccessLevel = Field(default="self_only", description="Phạm vi truy cập dữ liệu")
    manager_id: UUID | None = Field(default=None, description="ID quản lý trực tiếp (cho team_scope)")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Conversation(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None = Field(default=None, description="Tiêu đề hội thoại")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Citation(BaseModel):
    chunk_id: str
    source_file: str
    title: str
    page_start: int | None = None
    page_end: int | None = None
    category: str
    is_official_policy: bool
    source_type: str = Field(default="", description="government_law | official_policy | public_template | synthetic | public_article")
    excerpt: str = Field(default="", description="Đoạn văn bản của chunk được dùng làm nguồn")


class Message(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(..., description="Nội dung tin nhắn")
    citations: list[Citation] = Field(default_factory=list, description="Trích dẫn nguồn (chỉ có ở tin nhắn assistant)")
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Độ tin cậy câu trả lời")
    escalated: bool = Field(default=False, description="Có bị escalate sang ticket không")
    ticket_id: UUID | None = None
    created_at: datetime | None = None


class TicketRequester(BaseModel):
    user_id: UUID
    role: Role
    department: str | None = None


class Ticket(BaseModel):
    id: UUID
    ticket_code: str = Field(..., description="Mã ticket, vd TCK-2026-000123")
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    requester_id: UUID
    employee_question: str = Field(..., description="Câu hỏi gốc của nhân viên")
    escalate_reason: EscalateReason
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    category: str | None = None
    target_department: TargetDepartment = Field(..., description="Phòng ban xử lý: C&B/ER/TA/L&D/HRBP")
    priority: TicketPriority
    status: TicketStatus = Field(default="open")
    assignee_id: UUID | None = Field(default=None, description="HR admin được gán xử lý")
    resolution_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class TicketDraft(BaseModel):
    """Phần của `Ticket` mà agent tự đủ dữ liệu để điền theo versioned
    ticket routing config. Backend chỉ cần bổ sung
    `id`/`ticket_code`/`conversation_id`/`message_id`/
    `requester_id`/`created_at` (đến từ phiên đăng nhập, ngoài phạm vi agent)
    rồi insert thẳng vào bảng `tickets`."""

    employee_question: str
    escalate_reason: EscalateReason
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    category: str | None = None
    target_department: TargetDepartment
    priority: TicketPriority


class AgentAnswer(BaseModel):
    """Contract duy nhất backend cần biết để gọi agent — xem docs/AGENT_API.md.
    Thay thế `ChatResponse` cũ (chỉ có `response`/`analysis` chết, mọi
    citation/confidence/escalate bị vứt bỏ ngay tại lớp API)."""

    response: str = Field(..., description="Phản hồi hiển thị cho user")
    intent: Intent
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    needs_clarification: bool = Field(default=False, description="True -> hiển thị clarifying_question, không có response cuối")
    clarifying_question: str | None = None
    escalate: bool = Field(default=False, description="True -> backend PHẢI tạo ticket từ ticket_draft")
    escalate_reason: EscalateReason | None = None
    ticket_draft: TicketDraft | None = Field(default=None, description="Chỉ có khi escalate=True")


class ChatResponse(AgentAnswer):
    pass


class Document(BaseModel):
    id: UUID
    source_file: str
    category: str
    status: DocumentStatus = Field(default="raw")
    source_type: DocumentSourceType
    is_official_policy: bool = Field(..., description="False nếu là template công khai/synthetic — KHÔNG phải chính sách công ty thật")
    caveat: str | None = Field(default=None, description="Cảnh báo/lưu ý khi trích dẫn tài liệu này")
    processed_path: str | None = None
    chunks_path: str | None = None
    chroma_indexed_at: datetime | None = Field(default=None, description="Thời điểm index vào Chroma Cloud")
    uploaded_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
