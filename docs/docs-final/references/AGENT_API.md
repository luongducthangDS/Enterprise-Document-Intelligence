# Agent API Contract

Điểm vào nội bộ của Agent là [`src/agents/service.py::answer(query: str, history: list[dict] | None = None) -> AgentAnswer`](../../src/agents/service.py). Không đọc `AgentState` (TypedDict nội bộ trong [`src/agents/state.py`](../../src/agents/state.py)) trực tiếp — nó có field runtime-only (`rewrite_count`, `hallucination_retry_count`, ...) không thuộc contract và có thể đổi bất cứ lúc nào theo nhu cầu nội bộ của graph.

```python
from src.agents.service import answer

result = await answer("Tôi được nghỉ mấy ngày phép năm?")  # -> AgentAnswer, lượt đầu tiên

# Lượt tiếp theo trong cùng hội thoại — caller tự truyền lại các lượt trước
# (agent KHÔNG tự lưu session, xem mục "State hội thoại đa lượt" bên dưới).
result2 = await answer(
    "Vậy nghỉ ốm thì sao?",
    history=[
        {"role": "user", "content": "Tôi được nghỉ mấy ngày phép năm?"},
        {"role": "assistant", "content": result.response},
    ],
)
```

Khi Agent và Backend deploy riêng, Backend chỉ gọi HTTP endpoint nội bộ `POST /api/v1/agent/query`. Endpoint cũ `POST /api/v1/chat` được giữ lại để tương thích với client Agent hiện có — từ 13/08/2026 nó **yêu cầu `X-Service-Token` như mọi route nội bộ khác** (trước đó đây là route nội bộ duy nhất không yêu cầu xác thực).

Các job admin (ingestion, index rebuild, evaluation) chạy qua nhóm route riêng `POST /api/v1/agent/jobs/*` + `GET /api/v1/agent/jobs/{job_id}` — contract đầy đủ ở [`AGENT_WORKERS.md`](AGENT_WORKERS.md).

## HTTP contract Backend ↔ Agent

```http
POST /api/v1/agent/query
X-Service-Token: <shared-secret>
X-Request-ID: <chat-request-id>
Content-Type: application/json
```

```json
{
  "query": "Tôi được nghỉ mấy ngày phép năm?",
  "request_id": "a4a13978-ef91-43c0-818e-f08f15e4d00c",
  "user_id": "2bb95df9-4544-42c2-b5f1-25a45d40e714",
  "department": "Engineering",
  "history": [
    {"role": "user", "content": "Tôi được nghỉ mấy ngày phép năm?"},
    {"role": "assistant", "content": "Bạn muốn hỏi phép năm hay nghỉ ốm?"}
  ]
}
```

`history` là field optional và backward-compatible. Backend lấy tối đa 8 message gần nhất từ conversation, loại message hiện tại để không gửi trùng, rồi gửi theo thứ tự cũ đến mới.

Response là `AgentAnswer` nguyên bản. `request_id`, `user_id` và `department` là trace context do Backend đã xác thực; Agent hiện không dùng chúng để truy cập dữ liệu cá nhân hoặc tự tạo ticket.

Hai service dùng cùng secret qua `AI_AGENT_SERVICE_TOKEN` ở Backend và `AGENT_SERVICE_TOKEN` ở Agent. Có thể để trống trong local development; môi trường deploy phải cấu hình secret và chỉ expose Agent trong private network.

`src/api/routes.py::POST /api/v1/chat` chỉ là một lớp mỏng gọi hàm này — `ChatResponse` kế thừa thẳng `AgentAnswer`, `ChatRequest` có thêm field `history: list[HistoryTurn]` (xem [`src/models/schemas.py`](../../src/models/schemas.py)).

## State hội thoại đa lượt

Agent vẫn **stateless** — không tự lưu session, không đọc Supabase `Conversation`/`Message` (bảng đó do backend quản lý). Mỗi lời gọi `answer()`/`POST /chat`, caller tự truyền lại các lượt gần nhất qua `history` (dạng `[{"role": "user"|"assistant", "content": str}, ...]`, thứ tự cũ → mới).

Node đầu tiên của graph (`condense_node`, [`src/agents/nodes/condense.py`](../../src/agents/nodes/condense.py)) dùng `history` để viết lại câu hỏi hiện tại thành 1 câu hỏi độc lập, tự chứa đủ ngữ cảnh (thay đại từ/tham chiếu mơ hồ bằng thực thể cụ thể, giữ lại dữ kiện định lượng đã nêu ở lượt trước) trước khi vào router/retrieval/generate. Không truyền `history` (hoặc `history=[]`) → bỏ qua bước này hoàn toàn, không tốn thêm LLM call — hành vi giống hệt trước khi có field này.

Chỉ `max_history_turns` lượt gần nhất (mặc định 8, `src/config.py`) được đưa vào prompt condense — hội thoại dài hơn bị cắt bớt phần cũ.

## Response shape (`AgentAnswer`)

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `response` | `str` | Văn bản hiển thị cho user. Khi `needs_clarification=True`, đây chính là câu hỏi làm rõ. |
| `intent` | `"greeting" \| "hr_question" \| "ambiguous" \| "out_of_scope_or_personal" \| "pure_statutory"` | Kết quả phân loại của router. Chỉ mang tính thông tin — hành vi backend cần quan tâm nằm ở `state`/`escalate`/`needs_clarification`, không phải suy luận lại từ `intent`. `pure_statutory` (NexaTech Type-C contract v3.1.0): câu hỏi luật/thủ tục nhà nước thuần tuý, agent từ chối trả lời, không retrieval, không ticket. |
| `state` | `"ANSWER" \| "ABSTAIN" \| "OUT_OF_SCOPE"` | Tri-state runtime bắt buộc theo NexaTech Type-C contract v3.1.0 (frozen) — tính tập trung trong `src/agents/service.py::_derive_runtime_state`. `ANSWER`: có câu trả lời (kể cả greeting/clarifying question). `ABSTAIN`: từ chối vì thiếu bằng chứng nội bộ hoặc cần dữ liệu cá nhân/con người xử lý — xem `reason_code`. `OUT_OF_SCOPE`: câu hỏi luật/thủ tục nhà nước thuần tuý, nằm ngoài phạm vi trợ lý chính sách nội bộ. Mặc định `ANSWER` nếu không set (backward-compat cho client cũ). |
| `reason_code` | `"missing_policy_evidence" \| "requires_live_personal_data" \| None` | Chỉ có giá trị khi `state="ABSTAIN"`; luôn `None` khi `state` khác. `missing_policy_evidence`: đã tìm nhưng không đủ căn cứ nội bộ (map từ `escalate_reason` ∈ `low_confidence`/`out_of_scope`/`competitor_question`). `requires_live_personal_data`: cần mở dữ liệu cá nhân/con người xử lý (map từ `escalate_reason` ∈ `personal_data_required`/`user_requested_human`/`human_first_required`). |
| `confidence_score` | `float \| None`, 0–1 | `None` khi không đi qua nhánh RAG (greeting/ambiguous). Không phải xác suất đúng theo nghĩa thống kê — là điểm liên quan của đoạn tốt nhất sau reranker, đã bị ép thấp nếu hallucination-check fail hoặc agent tự nhận không đủ thông tin. |
| `citations` | `list[Citation]` | Rỗng nếu không có nguồn nào được dùng. Mỗi `Citation` có `source_file`, `title`, `category`, `page_start`/`page_end` (`None` nếu tài liệu không phải PDF phân trang), `is_official_policy` và `excerpt` là nội dung chunk được dùng làm nguồn. |
| `needs_clarification` | `bool` | `True` → hiển thị `clarifying_question`/`response` và chờ câu trả lời tiếp theo của user; **không có gì để lưu như một câu trả lời "cuối"**. |
| `clarifying_question` | `str \| None` | Chỉ có khi `needs_clarification=True`. |
| `escalate` | `bool` | `True` → **backend phải tạo ticket** từ `ticket_draft`. Agent không tự ghi Supabase (ngoài phạm vi agent — xem CLAUDE.md). |
| `escalate_reason` | `str \| None` | Một trong `low_confidence`, `out_of_scope`, `personal_data_required`, `user_requested_human`, `competitor_question`, `human_first_required`. |
| `ticket_draft` | `TicketDraft \| None` | Chỉ có khi `escalate=True`. |
| `boundary` | `BoundaryDecision \| None` | Canonical runtime decision theo `Runtime-Revised Canonical Scenario Registry`. Nullable để client bản cũ không vỡ. Client mới render action theo `boundary.runtime_action`, **không** suy diễn từ nội dung `response`. |

## Ví dụ `state`/`reason_code` theo NexaTech Type-C contract v3.1.0

**ANSWER** (trả lời được từ dữ liệu nội bộ):
```json
{
  "state": "ANSWER",
  "reason_code": null,
  "response": "Theo Chính sách Công tác phí của NexaTech, taxi/Grab được thanh toán tối đa 300.000 VNĐ/ngày [Nguồn 1].",
  "citations": [{"source_file": "12_quy-che-cong-tac-phi.md", "..." : "..."}]
}
```

**ABSTAIN / `missing_policy_evidence`** (đã tìm nhưng không đủ căn cứ nội bộ):
```json
{
  "state": "ABSTAIN",
  "reason_code": "missing_policy_evidence",
  "response": "Xin lỗi, mình chưa đủ căn cứ để trả lời chắc chắn câu hỏi này. Mình đã chuẩn bị nội dung yêu cầu hỗ trợ để bạn chuyển tới người phụ trách.",
  "citations": []
}
```

**ABSTAIN / `requires_live_personal_data`** (cần dữ liệu cá nhân/con người xử lý):
```json
{
  "state": "ABSTAIN",
  "reason_code": "requires_live_personal_data",
  "response": "Xin lỗi, mình chưa đủ căn cứ để trả lời chắc chắn câu hỏi này. Người phụ trách nội dung này là HR Ops.",
  "citations": []
}
```

**OUT_OF_SCOPE** (câu hỏi luật/thủ tục nhà nước thuần tuý — không retrieval, không ticket):
```json
{
  "state": "OUT_OF_SCOPE",
  "reason_code": null,
  "response": "[OUT_OF_SCOPE] NexaBot chỉ hỗ trợ giải đáp các quy định và chính sách nội bộ do NexaTech ban hành. ...",
  "citations": []
}
```

## Khi nào tạo ticket, khi nào không

**Luật MVP-1: hễ response có `boundary` thì KHÔNG tạo ticket, bất kể `escalate` bằng gì.**
Trần action của MVP-1 chỉ gồm `NONE`/`LINK_ONLY`/`PREFILL_DRAFT`; không action nào tạo workflow. `escalate=True` ở đây chỉ có nghĩa "cần người phụ trách xử lý", không phải "đã tạo yêu cầu".

| tình huống | tạo ticket? | backend làm gì |
|---|---|---|
| có `boundary` (mọi `escalate`/`escalate_reason`) | **Không** | Hiển thị `response` + render theo `boundary.runtime_action` |
| `escalate=False` + `escalate_reason="human_first_required"` | Không | Scenario `HUMAN_FIRST`/`Critical`: chỉ hiển thị người phụ trách và kênh an toàn |
| `escalate=False` + `escalate_reason="competitor_question"` | Không | Câu hỏi chính sách công ty khác — agent đã tự từ chối lịch sự |
| `escalate=False` + `escalate_reason=None` | Không | Câu trả lời bình thường |
| `escalate=True` + **không có** `boundary` (agent bản cũ) | Có | Đường legacy giữ nguyên để không phá backward compatibility |

```python
if result.escalate and result.boundary is None:
    # Đường LEGACY duy nhất còn ghi ticket: agent bản cũ chưa gửi boundary.
    ticket_id = create_ticket(result.ticket_draft, requester_id=..., conversation_id=..., message_id=...)
else:
    # MVP-1 boundary flow: 0 ticket, 0 workflow record.
    ...
```

`messages.escalated=True` cùng `messages.ticket_id=NULL` là trạng thái **hợp lệ và mong đợi** của boundary flow. Không UI/API nào được suy ra từ `escalated` rằng ticket đã được tạo.

## `BoundaryDecision`

Nguồn: `Runtime-Revised Canonical Scenario Registry` trong `docs/project/hr_interaction_boundary_plan.md`, biểu diễn machine-readable ở `src/agents/resources/scenario_registry.json`.

| Field | Ý nghĩa |
|---|---|
| `scenario_id`, `scenario_name` | 1–64, `null` khi không khớp scenario nào (`resolution="fallback"`). |
| `service_code`, `service_name` | HR service sở hữu scenario. |
| `assistant_role` | `ANSWER` / `GUIDE` / `PREPARE_AND_HANDOFF` / `HUMAN_FIRST`. |
| `sensitivity` | `Low` / `Medium` / `High` / `Critical`. |
| `runtime_source_status` | Thực tế runtime của nguồn (`KNOWLEDGE`, `EXTERNAL_ASSUMED`, `NOT_AVAILABLE`...). Là **engineering metadata**, không hiển thị thẳng cho user. |
| `source_of_truth_label` | Nhãn user-facing tương ứng, đã bỏ mọi từ kỹ thuật. |
| `max_runtime_action` | Trần theo registry, có thể là `CREATE_CASE` (MVP-2). |
| `runtime_action` | Mức được phép **ngay bây giờ** sau khi cắt theo capability MVP-1 — luôn thuộc `NONE`/`LINK_ONLY`/`PREFILL_DRAFT`. Đây là field client phải dùng để render. |
| `mvp_phase` | `MVP_1` / `MVP_2` / `FUTURE` / `OUT_OF_MVP`. |
| `handoff_target` | `{type, code, name, contact_label}` hoặc `null`. Không chứa URL. |
| `user_facing_action_label` | `null` / `"Hướng dẫn gửi"` / `"Chuẩn bị yêu cầu"`. |
| `allowed_data_fields` | Allowlist field được phép thu, kèm `pii_class` và `storage_policy`. Field không có trong danh sách là **không được hỏi**. |
| `resolution` | `registry` hoặc `fallback`. |

Ba điều client tuyệt đối không được làm với decision này: nói yêu cầu đã được gửi khi `runtime_action` là `PREFILL_DRAFT`; tạo/hiển thị workflow khi `assistant_role="HUMAN_FIRST"`; và hiển thị nhãn kỹ thuật của `runtime_source_status`.

## `TicketDraft`

Khớp versioned config `src/agents/resources/ticket_routing_rules.json`, thiếu đúng những field chỉ backend/phiên đăng nhập mới biết:

| Field | Nguồn |
|---|---|
| `employee_question`, `escalate_reason`, `confidence_score`, `category`, `target_department`, `priority` | Agent điền sẵn |

> `ticket_draft` là **legacy/compatibility payload**: với boundary flow MVP-1 nó không được persist thành ticket. Giữ lại để agent/backend bản cũ không vỡ contract.
| `id`, `ticket_code`, `conversation_id`, `message_id`, `requester_id`, `status`, `created_at` | Backend tự sinh/lấy từ phiên đăng nhập, rồi insert thẳng vào bảng `tickets` (schema `Ticket` trong `schemas.py`, khớp `supabase/migrations/0001_initial_schema.sql`) |

`target_department` là một trong `CB` (Comp & Benefits), `ER` (Employee Relations), `TA` (Talent Acquisition), `LD` (Learning & Development), `HRBP` (fallback chung) — xem mô tả đầy đủ từng phòng ban trong `ticket_routing_rules.json::departments`.

## Rendering `citations`

Mỗi `Citation.is_official_policy=False` nghĩa là nguồn đến từ template công khai/tài liệu synthetic — **không phải chính sách chính thức của công ty**. Prompt sinh câu trả lời yêu cầu cảnh báo một lần trong `response`; citation được truyền bằng dữ liệu có cấu trúc và không bị nối lại thành footer văn bản. Backend nên gộp các chunk cùng `source_file` thành một citation card để tránh lặp tên tài liệu, đồng thời vẫn hiển thị cảnh báo nguồn không chính thức.

## Streaming end-to-end (`astream_answer` + SSE)

Streaming đã được nối qua cả ba lớp:

- Backend gọi Agent qua `POST /api/v1/agent/query/stream`.
- Frontend gọi Backend qua `POST /api/v1/chat/requests/stream`.
- Contract polling cũ vẫn được giữ để retry và phục hồi khi kết nối SSE bị ngắt.

Bản streaming nội bộ: [`src/agents/service.py::astream_answer(query, history=None) -> AsyncIterator[dict]`](../../src/agents/service.py).

**Quyết định kiến trúc quan trọng — KHÔNG stream token thô từ LLM.** `hallucination_check`/`confidence`/`redact_pii` chạy SAU khi model sinh xong câu trả lời và có thể FAIL/retry/cap điểm/che PII — tức có thể huỷ hoặc sửa toàn bộ nội dung. Stream token sống nghĩa là user thấy nội dung TRƯỚC KHI qua các lớp guardrail đó — đi ngược triết lý an toàn của cả pipeline (xem [`AI_SAFETY_GUARDRAILS.md`](AI_SAFETY_GUARDRAILS.md)). Vì vậy tách 2 luồng:

1. **Tiến trình (`status`/`tool_start`/`tool_end`)** — phát LIVE ngay khi mỗi node LangGraph hoàn thành, chỉ là metadata (node nào vừa chạy xong), không chứa nội dung câu trả lời → an toàn tuyệt đối, giải quyết đúng vấn đề "màn hình chết".
2. **Nội dung (`answer_delta`/`citation`)** — chỉ phát SAU KHI graph chạy xong toàn bộ, đã qua mọi guardrail giống hệt `answer()`, rồi chia nhỏ theo cụm ~15 từ để tạo hiệu ứng gõ chữ ở client. **Không giảm latency tới ký tự đầu tiên của câu trả lời** — đây là đánh đổi có chủ đích, không phải giới hạn chưa biết.

Event shape (mỗi item là 1 dict, backend tự quyết định đóng gói SSE/WebSocket):

| `type` | Field khác | Khi nào phát |
|---|---|---|
| `status` | `value: str` | Sau khi 1 node "đáng chờ" (condense có history/router/rewrite/generate/hallucination_check/escalate_ticket) chạy xong |
| `tool_start` / `tool_end` | `tool: str` (`"hr_policy_search"`) | Bọc quanh node `retrieve` |
| `answer_delta` | `content: str` | Sau khi graph xong, câu trả lời đã duyệt được chia nhỏ theo cụm từ |
| `citation` | `source`, `title`, `page_start`, `is_official_policy` | 1 event/citation, sau `answer_delta` cuối |
| `done` | Các field điều khiển (gồm `state`, `reason_code` — xem bảng `AgentAnswer` ở trên) và `answer: AgentAnswer` | Event cuối của Agent; `answer` là contract hoàn chỉnh để Backend kiểm tra và persist. `state`/`reason_code` lặp lại ở top-level để Backend không phải đọc sâu vào `answer` chỉ để định tuyến UI. |
| `error` | `message: str` | Khi graph lỗi giữa chừng — stream dừng ngay sau event này, không có `done` |

```python
from src.agents.service import astream_answer

async for event in astream_answer("Tôi được nghỉ mấy ngày phép năm?"):
    ...  # endpoint Agent đóng gói mỗi event thành SSE
```

Backend bổ sung event `request` ở đầu stream, `heartbeat` mỗi 15 giây chờ và `result` sau khi đã commit kết quả vào CSDL. Frontend chỉ coi `result` là điểm hoàn tất; nếu kết nối đứt sau event `request`, frontend dùng `chat_request_id` để quay về polling mà không tạo câu hỏi trùng.

## Giới hạn đã biết

- **Latency tới câu trả lời cuối cùng**: p50 ~15-35s cho câu hỏi cần RAG đầy đủ (router → retrieve → grade → generate → hallucination-check → confidence), tuỳ tải hệ thống — `astream_answer` cho phản hồi tiến trình sớm hơn nhưng KHÔNG rút ngắn tổng thời gian này. Chưa tối ưu trong đợt này — xem ghi chú trong `eval/results/report.md`.
- **Multi-turn qua `history`, không qua session ở agent.** Xem mục "State hội thoại đa lượt" ở trên — backend/caller chịu trách nhiệm lưu trữ và truyền lại lịch sử mỗi lần gọi, agent không tự nhớ.
- **Chưa xử lý câu hỏi tổng hợp nhiều tài liệu trong 1 lượt** (vd "tổng hợp tất cả quyền lợi khi nghỉ việc" cần gộp OT + phép + trợ cấp thôi việc + BHXH) — retrieval hiện chỉ chạy 1 lần cho toàn câu hỏi, chưa có query decomposition.
