from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.agents.state import Intent, RuntimeReasonCode, RuntimeState


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
    tenant_id: str = Field(..., min_length=1, max_length=128)
    department: str = Field(..., min_length=1, max_length=128)
    user_role: str = Field(..., min_length=1, max_length=64)
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
    department: str = Field(default="HR", max_length=128)
    source_type: str = Field(default="official_policy", max_length=64)
    is_official_policy: bool = True
    caveat: str = Field(default="", max_length=500)
    # Tài liệu đi qua đường upload là do doanh nghiệp khách hàng cung cấp — mặc
    # định đúng cho production. Corpus demo/synthetic KHÔNG đi qua đường này (nó
    # được nạp offline bằng scripts/rag_pipeline/build_chunks.py từ registry).
    authority: str = Field(default="tenant_official_policy", max_length=64)
    provenance: str = Field(default="customer_provided", max_length=64)
    tenant: str = Field(..., min_length=1, max_length=128, description="Slug tenant đã xác thực; bắt buộc cho mọi write")
    access_scope: Literal["COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"] = "RESTRICTED"
    authorized_role: str = Field(default="", max_length=64)
    owner_user_id: str = Field(..., min_length=1, max_length=128)
    authorization_source: Literal["RUNTIME_UPLOAD"] = "RUNTIME_UPLOAD"
    publication_status: Literal["active", "draft", "superseded", "archived"] = "active"
    artifact_state: Literal["frozen", "draft"] = "frozen"
    retrieval_enabled: bool = True
    expiry_date: str = Field(default="9999-12-31", max_length=10)


class IndexRebuildTarget(BaseModel):
    document_id: str | None = Field(default=None, max_length=128)
    source_file: str = Field(..., min_length=1, max_length=255)


class IndexRebuildJobRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    tenant: str = Field(..., min_length=1, max_length=128)
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
# "competitor_question" và "human_first_required" không tạo ticket
# (escalate=False) — xem escalate_node trong src/agents/nodes/escalation.py —
# nhưng vẫn cần xuất hiện trong Literal này vì AgentAnswer.escalate_reason phản
# ánh giá trị thật agent trả về.
EscalateReason = Literal[
    "low_confidence",
    "out_of_scope",
    "personal_data_required",
    "user_requested_human",
    "competitor_question",
    "human_first_required",
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
    """`chunk_id`/`source_file` là diagnostics kỹ thuật cho backend/audit — KHÔNG
    được đưa vào text `response` cho nhân viên (xem generate_node/_GENERATE_SYSTEM
    trong src/agents/nodes/generation.py). Client hiển thị nguồn cho người dùng
    nên ghép `title` + `source_section` (vd "Chính sách Nghỉ phép · 4.1. Số ngày
    nghỉ phép năm tiêu chuẩn"), không dùng `source_file`/`chunk_id`.

    3 trục độc lập mô tả một tài liệu (đừng nhầm lẫn):
    - data_origin (= `source_type`): nguồn gốc dữ liệu — synthetic/official_policy/
      government_law/... "synthetic" mô tả CÁCH tài liệu được tạo ra, không nói
      gì về việc nó có được duyệt dùng hay không.
    - runtime_authority (= `authority`): thẩm quyền được PHÉP DÙNG để trả lời tại
      runtime — vd "tenant_official_policy" nghĩa là agent được coi đây là chính
      sách nội bộ chính thức của tenant (kể cả khi data_origin=synthetic, trong
      tenant giả lập nó VẪN đóng vai chính sách đã duyệt).
    - policy_status (= `policy_status`): vòng đời PHÊ DUYỆT thật của tài liệu
      (active/superseded/draft, từ registry publication_status) — trục còn thiếu
      trước đây khiến "synthetic" dễ bị đọc nhầm thành "chưa duyệt".
    """

    chunk_id: str
    source_file: str
    title: str
    page_start: int | None = None
    page_end: int | None = None
    sheet_start: str | None = None
    sheet_end: str | None = None
    department: str = "HR"
    category: str
    is_official_policy: bool
    source_type: str = Field(default="", description="government_law | official_policy | public_template | synthetic | public_article — data_origin, KHÔNG phải trạng thái phê duyệt")
    authority: str = Field(default="", description="Thẩm quyền runtime — vd tenant_official_policy | government_law | public_reference | public_template")
    provenance: str = Field(default="", description="Nguồn gốc chi tiết — vd customer_provided | synthetic_demo | government_source")
    tenant: str = Field(default="", description="Slug doanh nghiệp sở hữu tài liệu, rỗng nếu không thuộc doanh nghiệp nào")
    source_section: str = Field(default="", description="Nhãn mục/điều khoản người dùng đọc được, vd '4.1. Số ngày nghỉ phép năm tiêu chuẩn' — dùng để hiển thị citation thay cho tên file kỹ thuật")
    policy_status: str = Field(default="", description="active | superseded | draft — vòng đời phê duyệt (registry publication_status), độc lập với source_type")
    excerpt: str = Field(default="", description="Đoạn văn bản của chunk được dùng làm nguồn")


class Message(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(..., description="Nội dung tin nhắn")
    citations: list[Citation] = Field(default_factory=list, description="Trích dẫn nguồn (chỉ có ở tin nhắn assistant)")
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Độ tin cậy câu trả lời")
    # escalated=True nghĩa là "cần người xử lý", KHÔNG phải "đã tạo ticket".
    # Boundary flow MVP-1 hợp lệ khi escalated=True và ticket_id=None.
    escalated: bool = Field(default=False, description="Có cần chuyển cho người phụ trách xử lý không")
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


AssistantRole = Literal["ANSWER", "GUIDE", "PREPARE_AND_HANDOFF", "HUMAN_FIRST"]
RuntimeAction = Literal["NONE", "LINK_ONLY", "PREFILL_DRAFT", "CREATE_CASE"]
Sensitivity = Literal["Low", "Medium", "High", "Critical"]
MvpPhase = Literal["MVP_1", "MVP_2", "FUTURE", "OUT_OF_MVP"]


class AllowedDataFieldDTO(BaseModel):
    """Field được phép thu cho scenario — allowlist, không phải gợi ý."""

    field_key: str
    label: str
    required_for_prefill: bool = False
    pii_class: Sensitivity
    storage_policy: Literal["do_not_store", "store_case_only", "store_message_ok", "store_metadata_only"]


class BoundaryDecisionDTO(BaseModel):
    """Canonical runtime decision theo Runtime-Revised Canonical Scenario Registry.

    `max_runtime_action` là trần theo registry (có thể là CREATE_CASE ở MVP-2),
    `runtime_action` là mức được phép ngay bây giờ sau khi cắt theo capability
    của MVP-1. Client phải render theo `runtime_action`, không phải theo trần.

    `source_of_truth_label` KHÔNG cùng trục với `Citation.policy_status`: đây là
    nhãn Ở MỨC SCENARIO ("nhóm câu hỏi này có nguồn trả lời đã duyệt/thuộc quy
    trình sản phẩm/chưa có nguồn hay không" — do scenario_registry.json quyết
    định, không phụ thuộc tài liệu nào được retrieve), còn `policy_status` là
    vòng đời phê duyệt Ở MỨC TÀI LIỆU cụ thể vừa được trích dẫn. Hai field có
    thể cùng xuất hiện trong 1 response mà không mâu thuẫn — chúng trả lời hai
    câu hỏi khác nhau, không phải cùng một khái niệm nói 2 lần.
    """

    scenario_id: int | None = None
    scenario_name: str | None = None
    service_code: str | None = None
    service_name: str | None = None
    assistant_role: AssistantRole
    sensitivity: Sensitivity
    runtime_source_status: str
    source_of_truth_label: str
    max_runtime_action: RuntimeAction
    runtime_action: RuntimeAction
    mvp_phase: MvpPhase
    handoff_target: dict[str, str] | None = None
    user_facing_action_label: str | None = None
    allowed_data_fields: list[AllowedDataFieldDTO] = Field(default_factory=list)
    runtime_behavior: str = ""
    resolution: Literal["registry", "fallback"] = "registry"


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
    escalate: bool = Field(
        default=False,
        description=(
            "True -> lượt này cần người phụ trách xử lý. KHÔNG đồng nghĩa tạo ticket: "
            "khi có `boundary`, backend không tạo workflow nào (MVP-1)."
        ),
    )
    escalate_reason: EscalateReason | None = None
    # Legacy/compatibility payload: chỉ đường không có `boundary` mới dùng nó để
    # insert ticket. Với boundary flow MVP-1 nó không được persist thành ticket.
    ticket_draft: TicketDraft | None = Field(
        default=None, description="Chỉ có khi escalate=True; chỉ được persist ở đường legacy không có boundary"
    )
    # Nullable để client bản cũ không vỡ; client mới render action theo
    # boundary.runtime_action thay vì suy diễn từ nội dung câu trả lời.
    boundary: BoundaryDecisionDTO | None = Field(
        default=None, description="Canonical runtime decision cho lượt trả lời này"
    )
    # Tri-state contract bắt buộc (NexaTech Type-C contract v3.1.0, frozen).
    # `state` KHÔNG thay thế `escalate`/`escalate_reason`/`needs_clarification`
    # (giữ nguyên cho client cũ) — đây là field tổng hợp mới cho client tuân thủ
    # contract cần đọc đúng 1 field duy nhất.
    state: RuntimeState = Field(default="ANSWER", description="ANSWER | ABSTAIN | OUT_OF_SCOPE")
    reason_code: RuntimeReasonCode | None = Field(
        default=None,
        description="missing_policy_evidence | requires_live_personal_data — chỉ có khi state=ABSTAIN",
    )
    answer_type: Literal["general_policy", "personalized", "not_applicable"] | None = Field(
        default=None,
        description=(
            "Model tự khai báo: 'general_policy' = nêu mức/quy định chung, KHÔNG khẳng định là số "
            "của riêng người hỏi; 'personalized' = số áp dụng đúng cho người hỏi vì họ đã tự cung cấp "
            "đủ điều kiện định tính; 'not_applicable' = câu trả lời không phải dạng quyền lợi/mức hưởng. "
            "KHÔNG suy ra field này từ confidence_score — hai khái niệm độc lập (xem src/agents/state.py::AnswerType). "
            "None khi response không đi qua generate_node (vd greeting/clarify/escalate/out_of_scope)."
        ),
    )


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
