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

Khi Agent và Backend deploy riêng, Backend chỉ gọi HTTP endpoint nội bộ `POST /api/v1/agent/query`. Endpoint cũ `POST /api/v1/chat` được giữ lại để tương thích với client Agent hiện có.

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
| `intent` | `"greeting" \| "hr_question" \| "ambiguous" \| "out_of_scope_or_personal"` | Kết quả phân loại của router. Chỉ mang tính thông tin — hành vi backend cần quan tâm nằm ở `escalate`/`needs_clarification`, không phải suy luận lại từ `intent`. |
| `confidence_score` | `float \| None`, 0–1 | `None` khi không đi qua nhánh RAG (greeting/ambiguous). Không phải xác suất đúng theo nghĩa thống kê — là điểm liên quan của đoạn tốt nhất sau reranker, đã bị ép thấp nếu hallucination-check fail hoặc agent tự nhận không đủ thông tin. |
| `citations` | `list[Citation]` | Rỗng nếu không có nguồn nào được dùng. Mỗi `Citation` có `source_file`, `title`, `category`, `page_start`/`page_end` (`None` nếu tài liệu không phải PDF phân trang), `is_official_policy`. |
| `needs_clarification` | `bool` | `True` → hiển thị `clarifying_question`/`response` và chờ câu trả lời tiếp theo của user; **không có gì để lưu như một câu trả lời "cuối"**. |
| `clarifying_question` | `str \| None` | Chỉ có khi `needs_clarification=True`. |
| `escalate` | `bool` | `True` → **backend phải tạo ticket** từ `ticket_draft`. Agent không tự ghi Supabase (ngoài phạm vi agent — xem CLAUDE.md). |
| `escalate_reason` | `str \| None` | Một trong `low_confidence`, `out_of_scope`, `personal_data_required`, `user_requested_human`, `competitor_question`. |
| `ticket_draft` | `TicketDraft \| None` | Chỉ có khi `escalate=True`. |

## Khi nào tạo ticket, khi nào không

`escalate=True` không phải lúc nào cũng đồng nghĩa "tạo ticket" theo trực giác — có đúng một ngoại lệ:

- **`escalate=True`** (mọi `escalate_reason` trừ `competitor_question`) → tạo ticket từ `ticket_draft`.
- **`escalate=False` + `escalate_reason="competitor_question"`** → **KHÔNG tạo ticket**. Đây là câu hỏi về chính sách của một công ty khác (Viettel, FPT, Samsung...) — không có gì để HR công ty mình xử lý, agent đã tự trả lời từ chối lịch sự trong `response`. Backend chỉ cần hiển thị `response`, không cần làm gì thêm.
- **`escalate=False` + `escalate_reason=None`** → câu trả lời bình thường, không escalate.

```python
if result.escalate:
    ticket_id = create_ticket(result.ticket_draft, requester_id=..., conversation_id=..., message_id=...)
    # result.ticket_draft đã có: employee_question, escalate_reason,
    # confidence_score, category, target_department, priority — backend chỉ
    # bổ sung những gì chỉ backend biết (ai hỏi, hội thoại nào).
else:
    # Không tạo ticket, kể cả khi escalate_reason == "competitor_question".
    ...
```

## `TicketDraft`

Khớp versioned config `src/agents/resources/ticket_routing_rules.json`, thiếu đúng những field chỉ backend/phiên đăng nhập mới biết:

| Field | Nguồn |
|---|---|
| `employee_question`, `escalate_reason`, `confidence_score`, `category`, `target_department`, `priority` | Agent điền sẵn |
| `id`, `ticket_code`, `conversation_id`, `message_id`, `requester_id`, `status`, `created_at` | Backend tự sinh/lấy từ phiên đăng nhập, rồi insert thẳng vào bảng `tickets` (schema `Ticket` trong `schemas.py`, khớp `supabase/migrations/0001_initial_schema.sql`) |

`target_department` là một trong `CB` (Comp & Benefits), `ER` (Employee Relations), `TA` (Talent Acquisition), `LD` (Learning & Development), `HRBP` (fallback chung) — xem mô tả đầy đủ từng phòng ban trong `ticket_routing_rules.json::departments`.

## Rendering `citations`

Mỗi `Citation.is_official_policy=False` nghĩa là nguồn đến từ template công khai/tài liệu synthetic — **không phải chính sách chính thức của công ty**. `response` đã tự kèm cảnh báo này trong văn bản khi cần (xem `finalize_node`), nhưng nếu backend/frontend render citation card riêng, nên hiển thị lại cảnh báo đó thay vì chỉ liệt kê tên tài liệu — tránh để user hiểu nhầm là quy định chính thức.

## Streaming (`astream_answer`) - future transport

`astream_answer()` hiện chỉ là capability Python nội bộ. MVP production vẫn dùng background task + REST polling; chưa có SSE endpoint ở Agent, BE proxy hay FE consumer. Không coi streaming là end-to-end cho tới khi cả ba lớp được triển khai và kiểm thử.

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
| `done` | `intent`, `confidence_score`, `needs_clarification`, `clarifying_question`, `escalate`, `escalate_reason`, `ticket_draft` | Event cuối cùng — tương đương phần metadata của `AgentAnswer` (trừ `response`/`citations` đã phát riêng ở trên) |
| `error` | `message: str` | Khi graph lỗi giữa chừng — stream dừng ngay sau event này, không có `done` |

```python
from src.agents.service import astream_answer

async for event in astream_answer("Tôi được nghỉ mấy ngày phép năm?"):
    ...  # backend tự chuyển thành SSE: f"data: {json.dumps(event)}\n\n"
```

Node nào chạy đủ nhanh/thuần code (`grade`/`confidence`/`finalize`, hoặc `condense` khi không có `history` — 0-cost skip) không phát `status` riêng, tránh spam.

## Giới hạn đã biết

- **Latency tới câu trả lời cuối cùng**: p50 ~15-35s cho câu hỏi cần RAG đầy đủ (router → retrieve → grade → generate → hallucination-check → confidence), tuỳ tải hệ thống — `astream_answer` cho phản hồi tiến trình sớm hơn nhưng KHÔNG rút ngắn tổng thời gian này. Chưa tối ưu trong đợt này — xem ghi chú trong `eval/results/report.md`.
- **Multi-turn qua `history`, không qua session ở agent.** Xem mục "State hội thoại đa lượt" ở trên — backend/caller chịu trách nhiệm lưu trữ và truyền lại lịch sử mỗi lần gọi, agent không tự nhớ.
- **Chưa xử lý câu hỏi tổng hợp nhiều tài liệu trong 1 lượt** (vd "tổng hợp tất cả quyền lợi khi nghỉ việc" cần gộp OT + phép + trợ cấp thôi việc + BHXH) — retrieval hiện chỉ chạy 1 lần cho toàn câu hỏi, chưa có query decomposition.
