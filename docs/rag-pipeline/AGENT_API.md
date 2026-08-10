# Agent API Contract

Điểm vào nội bộ của Agent là [`src/agents/service.py::answer(query: str) -> AgentAnswer`](../../src/agents/service.py). Không đọc `AgentState` (TypedDict nội bộ trong [`src/agents/state.py`](../../src/agents/state.py)) trực tiếp — nó có field runtime-only (`rewrite_count`, `hallucination_retry_count`, ...) không thuộc contract và có thể đổi bất cứ lúc nào theo nhu cầu nội bộ của graph.

```python
from src.agents.service import answer

result = await answer("Tôi được nghỉ mấy ngày phép năm?")  # -> AgentAnswer
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
  "department": "Engineering"
}
```

Response là `AgentAnswer` nguyên bản. `request_id`, `user_id` và `department` là trace context do Backend đã xác thực; Agent hiện không dùng chúng để truy cập dữ liệu cá nhân hoặc tự tạo ticket.

Hai service dùng cùng secret qua `AI_AGENT_SERVICE_TOKEN` ở Backend và `AGENT_SERVICE_TOKEN` ở Agent. Có thể để trống trong local development; môi trường deploy phải cấu hình secret và chỉ expose Agent trong private network.

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

Khớp `data/metadata/ticket_routing_rules.json::ticket_template`, thiếu đúng những field chỉ backend/phiên đăng nhập mới biết:

| Field | Nguồn |
|---|---|
| `employee_question`, `escalate_reason`, `confidence_score`, `category`, `target_department`, `priority` | Agent điền sẵn |
| `id`, `ticket_code`, `conversation_id`, `message_id`, `requester_id`, `status`, `created_at` | Backend tự sinh/lấy từ phiên đăng nhập, rồi insert thẳng vào bảng `tickets` (schema `Ticket` trong `schemas.py`, khớp `supabase/migrations/0001_initial_schema.sql`) |

`target_department` là một trong `CB` (Comp & Benefits), `ER` (Employee Relations), `TA` (Talent Acquisition), `LD` (Learning & Development), `HRBP` (fallback chung) — xem mô tả đầy đủ từng phòng ban trong `ticket_routing_rules.json::departments`.

## Rendering `citations`

Mỗi `Citation.is_official_policy=False` nghĩa là nguồn đến từ template công khai/tài liệu synthetic — **không phải chính sách chính thức của công ty**. `response` đã tự kèm cảnh báo này trong văn bản khi cần (xem `finalize_node`), nhưng nếu backend/frontend render citation card riêng, nên hiển thị lại cảnh báo đó thay vì chỉ liệt kê tên tài liệu — tránh để user hiểu nhầm là quy định chính thức.

## Giới hạn đã biết

- **Latency**: p50 ~15-35s cho câu hỏi cần RAG đầy đủ (router → retrieve → grade → generate → hallucination-check → confidence), tuỳ tải hệ thống. Chưa tối ưu trong đợt này — xem ghi chú trong `eval/results/report.md`. Backend nên có timeout/loading state phù hợp, không giả định phản hồi tức thời.
- **Không có streaming.** `answer()` trả về sau khi toàn bộ graph chạy xong.
- **Không có state hội thoại đa lượt.** Mỗi lời gọi `answer(query)` độc lập — agent không tự nhớ câu hỏi trước đó. Nếu cần multi-turn, backend phải tự truyền lại ngữ cảnh vào `query` (chưa có API riêng cho việc này).
