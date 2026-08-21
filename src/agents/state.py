from __future__ import annotations

from typing import Literal, TypedDict

Intent = Literal["greeting", "hr_question", "ambiguous", "out_of_scope_or_personal", "pure_statutory"]

# Tri-state runtime contract (NexaTech Type-C contract v3.1.0, frozen):
# ANSWER      — trả lời được (kể cả greeting/clarifying question).
# ABSTAIN     — không trả lời vì thiếu bằng chứng nội bộ hoặc cần dữ liệu cá
#               nhân/con người xử lý (xem RuntimeReasonCode).
# OUT_OF_SCOPE — câu hỏi pháp luật/thủ tục nhà nước thuần tuý, KHÔNG thuộc
#               phạm vi trợ lý chính sách nội bộ; không retrieval, không ticket.
RuntimeState = Literal["ANSWER", "ABSTAIN", "OUT_OF_SCOPE"]
RuntimeReasonCode = Literal["missing_policy_evidence", "requires_live_personal_data"]

# Tín hiệu MODEL TỰ KHAI BÁO (không phải confidence_score) cho biết câu trả lời
# có personalize theo thông tin người hỏi tự cung cấp hay không — xem
# ANSWER_TYPE_MARKER trong nodes/generation.py. Tách khỏi confidence_score vì
# đó là hai câu hỏi khác nhau: confidence_score đo "đoạn trích có liên quan +
# câu trả lời có bám sát đoạn trích không", còn answer_type trả lời "câu trả
# lời có đang khẳng định một con số RIÊNG cho người hỏi hay chỉ nêu mức chung".
# general_policy   — nêu mức/tiêu chuẩn áp dụng chung, KHÔNG khẳng định số cụ
#                     thể là của riêng người hỏi (mặc định khi request không
#                     kèm hồ sơ nhân viên và câu hỏi/lịch sử không tự nêu đủ
#                     điều kiện định tính khớp chính sách).
# personalized     — model xác định được số/kết quả áp dụng đúng cho người hỏi
#                     vì chính họ đã nêu đủ điều kiện định tính trong câu hỏi
#                     hoặc lịch sử hội thoại (vd tự nói rõ thâm niên, loại công
#                     việc...).
# not_applicable    — câu trả lời không phải dạng quyền lợi/mức hưởng (vd quy
#                     trình, thủ tục) nên khái niệm personalize không áp dụng.
AnswerType = Literal["general_policy", "personalized", "not_applicable"]


class RetrievedChunk(TypedDict):
    chunk_id: str
    text: str
    source_file: str
    title: str
    department: str
    category: str
    is_official_policy: bool
    # government_law | official_policy | public_template | synthetic |
    # public_article — cần bản đầy đủ (không chỉ cờ is_official_policy nhị phân)
    # để generate_node xếp được 3 bậc ưu tiên khi các nguồn nói khác nhau.
    source_type: str
    # Taxonomy 2 chiều (xem src/ingestion/metadata.py): authority quyết định
    # thẩm quyền của nguồn, provenance quyết định nguồn gốc thật, tenant cho
    # biết tài liệu thuộc doanh nghiệp nào ("" = không thuộc doanh nghiệp nào).
    authority: str
    provenance: str
    tenant: str
    # Cảnh báo tự do từ registry (vd thời hiệu chưa xác minh) — đưa vào prompt
    # cùng nhãn nguồn, xem _origin_label trong nodes/generation.py.
    caveat: str
    # Đường dẫn heading trong tài liệu gốc (vd "4. Nghỉ phép năm > 4.1. Số ngày
    # nghỉ phép năm tiêu chuẩn"), có sẵn trong Chroma metadata từ chunk_builder
    # nhưng trước đây bị bỏ khi build RetrievedChunk. Dùng để (1) hiển thị
    # citation người dùng đọc được ("Nguồn: Chính sách Nghỉ phép · Điều 4.1")
    # thay vì tên file kỹ thuật, và (2) phân biệt điều khoản chính sách với mục
    # FAQ khi cùng nói về một chủ đề — xem _is_faq_heading trong nodes/generation.py.
    heading_path: str
    # active | superseded | draft — vòng đời PHÊ DUYỆT của tài liệu (registry
    # publication_status), KHÔNG cùng trục với source_type (nguồn gốc dữ liệu:
    # synthetic/official_policy/...) hay authority (thẩm quyền runtime). Một
    # tài liệu synthetic vẫn có thể policy_status=active trong tenant giả lập —
    # "synthetic" không đồng nghĩa "chưa duyệt". Xem ghi chú 3 trục trong
    # src/models/schemas.py::Citation.
    policy_status: str
    page_start: int | None
    page_end: int | None
    sheet_start: str | None
    sheet_end: str | None
    distance: float
    score: float | None


class Citation(TypedDict):
    chunk_id: str
    source_file: str
    title: str
    department: str
    category: str
    page_start: int | None
    page_end: int | None
    sheet_start: str | None
    sheet_end: str | None
    is_official_policy: bool
    # government_law | official_policy | public_template | synthetic |
    # public_article — bản đầy đủ của is_official_policy, để backend/FE phân
    # biệt được luật tham khảo với chính sách nội bộ thay vì chỉ có cờ nhị phân.
    source_type: str
    authority: str
    provenance: str
    tenant: str
    # Nhãn mục/điều khoản NGƯỜI DÙNG ĐỌC ĐƯỢC (vd "4.1. Số ngày nghỉ phép năm
    # tiêu chuẩn"), rút từ heading_path — client render "Nguồn: {title} · {source_section}"
    # thay vì lộ chunk_id/tên file kỹ thuật ra UI.
    source_section: str
    policy_status: str
    excerpt: str


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent RAG (HR Document Intelligence).

    Mỗi node đọc và ghi vào state này. total=False cho phép tất cả fields là optional.
    """

    query: str
    tenant_id: str
    user_id: str
    department: str
    user_role: str
    groups: list[str]
    permissions: list[str]
    request_id: str

    # Canonical runtime decision từ Runtime-Revised Canonical Scenario Registry

    # (src/agents/boundary.py). Quyết định assistant được phép làm gì với câu
    # hỏi này: scenario, assistant_role, sensitivity, trần action, người phụ
    # trách, field dữ liệu được phép thu. Có mặt từ node `boundary` trở đi.
    boundary: dict
    # Các lượt hội thoại trước đó (cũ -> mới), do caller truyền vào — agent
    # không tự lưu session. Rỗng ở lượt đầu tiên.
    history: list[dict]
    # Câu hỏi hiện tại đã viết lại thành câu hỏi độc lập, mang đủ ngữ cảnh cần
    # thiết từ `history` (condense_node). Không có `history` thì bằng `query`.
    condensed_query: str
    intent: Intent
    rewritten_query: str
    retrieved_chunks: list[RetrievedChunk]
    # Tập chunk thực sự được viện dẫn, theo đúng thứ tự [Nguồn N] đã đánh lại
    # trong generated_answer. Bước hallucination check dựng context từ đây.
    cited_chunks: list[RetrievedChunk]
    citations: list[Citation]
    generated_answer: str
    # False khi generate_node thấy context không chứa thông tin cụ thể được hỏi
    # (model phát ra INSUFFICIENT_MARKER). confidence_node dùng để ép điểm xuống
    # dưới ngưỡng escalate.
    answerable: bool
    # Xem docstring AnswerType — KHÔNG dùng confidence_score để suy ra field này.
    answer_type: AnswerType
    confidence_score: float
    needs_clarification: bool
    clarifying_question: str
    escalate: bool
    escalate_reason: str
    # Tri-state runtime contract — tính tập trung trong src/agents/service.py
    # (_derive_runtime_state), KHÔNG do node lẻ tự set, để tránh một nhánh quên
    # gán và rơi về None âm thầm.
    state: RuntimeState
    reason_code: RuntimeReasonCode | None
    ticket_category: str
    ticket_department: str
    ticket_priority: str
    rewrite_count: int
    hallucination_passed: bool
    hallucination_retry_count: int
    # "deterministic_numeric_grounding" | "llm_judge" — audit: câu trả lời được
    # chấm bằng lớp tất định (số liệu khớp/không khớp đoạn trích) hay phải rơi
    # xuống LLM (câu trả lời không có số liệu để so khớp).
    hallucination_check_method: str
    response: str
    error: str
    metadata: dict
    # Guardrail kỹ thuật (src/agents/guardrails.py) — cờ audit, không phải
    # điều khiển luồng. True khi phát hiện câu nghi injection trong câu hỏi
    # hoặc trong chunk RAG (chunk đã bị cắt trước khi vào prompt bất kể cờ
    # này), hoặc khi response cuối có PII bị che.
    guardrail_injection_detected: bool
    guardrail_pii_redacted: bool
    # Telemetry cho escalation guard (router._guard_escalation) — cờ quan sát,
    # không điều khiển luồng. Chỉ có mặt khi fast router định escalate:
    #   verifier_called       — có trả tiền cho 1 LLM call CÓ thinking không
    #                           (False = heuristic tầng 1-2 đã chốt, 0 LLM).
    #   verifier_changed_route — verifier có ĐỔI kết quả không (cứu về
    #                           hr_question) hay chỉ xác nhận điều hiển nhiên.
    #   verifier_latency_ms   — thời gian riêng của lệnh gọi verifier.
    # Ba trường này cho phép tính trực tiếp từ log production:
    #   verifier_trigger_rate = #verifier_called / #request
    #   verifier_useful_rate  = #verifier_changed_route / #verifier_called
    # `useful_rate` là metric quyết định: nếu nó tụt (verifier chủ yếu xác nhận
    # điều đã rõ) thì mới đáng thêm tầng pre-filter phía trước.
    verifier_called: bool
    verifier_changed_route: bool
    verifier_latency_ms: int
