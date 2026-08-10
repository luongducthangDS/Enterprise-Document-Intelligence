# Tích hợp Agent và Backend

Tài liệu này mô tả cách HR Policy Agent và Backend giao tiếp với nhau sau khi được tách thành hai service. Mục tiêu là giúp dev mới biết phải đọc file nào, dữ liệu đi qua đâu, và không vô tình đưa chi tiết nội bộ của Agent ra Frontend.

## 1. Mục tiêu

- Agent chịu trách nhiệm hiểu câu hỏi HR, tìm tài liệu, trả lời, yêu cầu làm rõ hoặc đề xuất escalation.
- Backend chịu trách nhiệm xác thực người dùng, lưu hội thoại, tạo ticket thật, xử lý timeout/lỗi và trả API đúng contract cho Frontend.
- Frontend chỉ gọi Backend. Frontend không gọi Agent trực tiếp.

Không đưa `AgentState`, số lần rewrite, retry LangGraph hoặc kết quả hallucination check ra API của Frontend.

## 2. Sơ đồ luồng

```text
Frontend
  |
  | POST /api/v1/chat/requests
  v
Backend Chat API
  |
  | tạo ChatRequestDB = QUEUED, lưu user message
  v
ChatService background task
  |
  | POST /api/v1/agent/query
  v
Agent Service (LangGraph)
  |
  | AgentAnswer JSON
  v
Backend adapter + database
  |
  | ChatRequestDB, MessageDB, TicketDB, citations
  v
Frontend polling GET /api/v1/chat/requests/{id}
```

## 3. Ownership

| Thành phần | Chịu trách nhiệm |
|---|---|
| Agent | Intent, retrieval, generation, citations, confidence, clarification, escalation draft |
| Backend | JWT/auth, RBAC, conversation history, database, ticket thật, timeout, retry API, polling response |
| Frontend | Gửi câu hỏi, polling, render answer/citation/clarification/error |

Agent không đọc database chat của Backend và không tự tạo `TicketDB`.

## 4. Internal API: Backend gọi Agent

Endpoint chạy trong Agent service:

```http
POST /api/v1/agent/query
X-Service-Token: <shared-secret>
X-Request-ID: <chat-request-id>
Content-Type: application/json
```

Request:

```json
{
  "query": "Tôi được nghỉ phép năm bao nhiêu ngày?",
  "request_id": "b1b8450a-7df2-4ad8-8e90-d5f7908aa1c2",
  "user_id": "6dd6581b-b5d4-4a19-b5fb-87802be2f911",
  "department": "Engineering"
}
```

Ý nghĩa request fields:

| Field | Dùng để làm gì? |
|---|---|
| `query` | Câu hỏi thực tế mà Agent xử lý |
| `request_id` | Theo dõi log xuyên Backend và Agent |
| `user_id` | Trace/audit; Agent hiện không truy cập dữ liệu cá nhân bằng field này |
| `department` | Trace context; sẵn sàng cho document filtering/RBAC sau này |

Backend đã xác thực JWT trước khi gửi request này. Agent không nhận JWT của Frontend.

## 5. Agent trả về gì?

Agent trả `AgentAnswer`:

```json
{
  "response": "Theo chính sách hiện hành, ...",
  "intent": "hr_question",
  "confidence_score": 0.92,
  "citations": [],
  "needs_clarification": false,
  "clarifying_question": null,
  "escalate": false,
  "escalate_reason": null,
  "ticket_draft": null
}
```

| Agent field | Backend xử lý | Frontend thấy? |
|---|---|---|
| `response` | Lưu answer hoặc assistant message | Có |
| `intent` | Chỉ dùng để map flow/log; không persist | Không |
| `confidence_score` | Lưu ở `MessageDB.confidence_score` | Chưa theo contract hiện tại |
| `citations` | Chuẩn hóa rồi lưu ở `ChatRequestDB` và `MessageDB` | Có |
| `needs_clarification` | Đặt state `CLARIFICATION_REQUIRED` | Có |
| `clarifying_question` | Lưu `clarification.question` và assistant message | Có |
| `escalate` | Nếu true, Backend tạo ticket thật | Gián tiếp qua response/state |
| `escalate_reason` | Lưu vào ticket khi có ticket | Không trực tiếp |
| `ticket_draft` | Dùng để tạo `TicketDB` | Không trực tiếp |

## 6. Mapping state đơn giản

| Agent result | `ChatRequestDB.state` | `answer_status` | Ticket |
|---|---|---|---|
| Trả lời bình thường | `COMPLETED` | `ANSWERED` | Không |
| Cần hỏi lại | `CLARIFICATION_REQUIRED` | `CLARIFICATION_REQUIRED` | Không |
| Không đủ evidence / cần HR | `REFUSED` | `INSUFFICIENT_EVIDENCE` | Có nếu `escalate=true` |
| Câu hỏi đối thủ cạnh tranh | `REFUSED` | `INSUFFICIENT_EVIDENCE` | Không |
| Agent timeout/lỗi | `FAILED` | `null` | Không |

`confidence_score` không tự quyết định state ở Backend. Backend ưu tiên các cờ mà Agent trả về: `needs_clarification` và `escalate`.

## 7. Citation được lưu như thế nào?

Agent citation có `chunk_id`, `source_file`, `title`, `page_start`, `page_end`, `category`, `is_official_policy`.

Backend thêm `citation_id` ổn định từ `chat_request_id + chunk_id`, sau đó lưu citation vào cả chat request và assistant message. Frontend tiếp tục dùng citation shape hiện có. Khi người dùng mở citation detail, `CitationService` tìm citation đã lưu và kiểm tra quyền đọc document trước khi trả dữ liệu.

Backend không tạo citation giả khi citation ID không tồn tại.

## 8. Ticket flow

Khi Agent trả:

```text
escalate = true
ticket_draft != null
```

Backend:

1. Tạo assistant message.
2. Tạo `TicketDB` từ `ticket_draft`.
3. Link `MessageDB.ticket_id` tới ticket vừa tạo.
4. Commit message, ticket và chat result cùng transaction.

Agent chỉ tạo draft. Các field như `ticket_code`, `requester_id`, `conversation_id`, `message_id` do Backend tạo.

Trường hợp đặc biệt: `escalate=false` và `escalate_reason="competitor_question"` không tạo ticket.

## 9. Timeout, retry và duplicate worker

- Timeout mặc định Backend gọi Agent: 60 giây.
- Timeout/lỗi Agent được map thành `FAILED` với `failure.code` như `AGENT_TIMEOUT`, `AGENT_UNAVAILABLE` hoặc `AGENT_SERVICE_ERROR`.
- API retry vẫn giữ nguyên: tạo chat request mới, giữ `parent_chat_request_id` để audit.
- Worker chỉ claim request đang `QUEUED`; worker chạy trùng không tạo message hoặc ticket lần hai.

Lưu ý: background task hiện dùng `asyncio.create_task`. Nó phù hợp MVP nhưng không durable nếu Backend process restart giữa chừng. Khi cần production reliability cao hơn, thay bằng queue/worker riêng là một phase độc lập, không phải phần Agent mapping.

## 10. Docker và local development

Compose root có ba service:

```text
agent    private network, port 8000 trong Docker
backend  public port 8000 cho Frontend
db       PostgreSQL
```

Trong Docker, Backend gọi:

```text
http://agent:8000/api/v1/agent
```

Khi chạy local từng service, Backend dùng mặc định:

```text
http://localhost:8001/api/v1/agent
```

Các biến quan trọng:

```text
AI_AGENT_SERVICE_URL
AI_AGENT_TIMEOUT_SECONDS
AI_AGENT_SERVICE_TOKEN
AGENT_SERVICE_TOKEN
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
JWT_SECRET_KEY
```

`AI_AGENT_SERVICE_TOKEN` và `AGENT_SERVICE_TOKEN` phải cùng giá trị.

## 11. File cần biết

| Mục đích | File |
|---|---|
| Agent HTTP endpoint | `src/api/routes.py` |
| Agent public Python interface | `src/agents/service.py` |
| Agent output schema | `src/models/schemas.py` |
| BE HTTP client gọi Agent | `backend/app/services/ai_agent_client.py` |
| Mapping AgentAnswer sang BE | `backend/app/services/agent_answer_adapter.py` |
| Chat orchestration | `backend/app/services/chat_service.py` |
| Tạo ticket từ Agent draft | `backend/app/services/ticket_service.py` |
| Citation detail và access control | `backend/app/services/citation_service.py` |
| FE chat API | `backend/app/api/v1/endpoints/chat.py` |

## 12. Cách kiểm tra nhanh

```bash
# Agent tests
pytest tests/ -v

# Backend tests
cd backend && pytest tests/ -v

# Chạy full stack
docker compose up --build
```

Test quan trọng đã có cho: normal answer, citation ID ổn định, clarification, escalation/ticket, timeout, retry, duplicate worker và citation access control.

## 13. Không làm trong phase này

- Không đổi FE chat contract.
- Không thêm DB migration.
- Không thay Agent `answer(query)`.
- Không gửi LangGraph internal state ra FE.
- Không thêm multi-turn context vào Agent input.
- Không thay `asyncio.create_task` bằng Celery/Redis/queue.
- Không hoàn thiện public Ticket API cho FE.
