# Tích hợp Agent - Backend - Frontend

## Kiến trúc hiện tại

```text
Next.js FE -> FastAPI BE -> FastAPI Agent/LangGraph -> ChromaDB + FPT.AI
                         -> PostgreSQL
```

- FE chỉ gọi BE; chat ưu tiên SSE và tự quay về polling khi stream bị ngắt.
- PostgreSQL của Supabase lưu `public.users`/`public.profiles`; BE xác minh mật khẩu đã hash, phát JWT và quản lý RBAC, conversation, persistence, citation, ticket.
- Agent stateless, phụ trách intent, RAG, generation, confidence, clarification và escalation draft.
- BE và Agent là hai service riêng; giao tiếp qua internal REST API.

## Luồng chat

```text
FE POST /chat/requests/stream
-> BE lưu user Message + ChatRequest=QUEUED
-> BE lấy tối đa 8 message gần nhất trong conversation
-> BE stream POST /agent/query/stream với query + optional history
-> Agent condense follow-up thành câu hỏi độc lập
-> Agent phát status/tool event, rồi answer_delta đã qua guardrail
-> BE adapter map state và lưu Message/Citation/Ticket
-> BE phát result sau khi commit; FE hiển thị câu trả lời cuối
-> nếu SSE đứt: FE poll GET /chat/requests/{id}
```

Agent trả các field chính:

```text
response, intent, confidence_score, citations,
needs_clarification, clarifying_question,
escalate, escalate_reason, ticket_draft
```

| Agent result | BE state | Kết quả |
|---|---|---|
| Answer | `COMPLETED` | Answer + citations |
| Cần làm rõ | `CLARIFICATION_REQUIRED` | FE gửi bổ sung trong cùng conversation |
| Thiếu bằng chứng / escalation | `REFUSED` | Tạo ticket khi `escalate=true` |
| Timeout / lỗi | `FAILED` | Safe error, có thể retry |

## Đã hoàn thành

- Tách Agent và BE thành hai service; thêm `AIAgentClient` và `AgentAnswerAdapter`.
- Mapping `AgentAnswer` sang `ChatRequestDB`, `MessageDB`, citations và `TicketDB`.
- Giữ nguyên FE contract; không expose LangGraph state/rewrite/hallucination nội bộ.
- Chuyển FE sang Next.js + TypeScript và nối API auth, chat, polling, retry, citation, document, index và evaluation.
- Multi-turn và clarification dùng history đã persist; Agent vẫn stateless và tự condense follow-up.
- Guardrail loại prompt injection khỏi RAG context và history trước node condense.
- PII được che ở response, citation metadata và citation excerpt trước khi FE nhìn thấy.
- Audit log chỉ ghi metadata/count, không ghi query hoặc đoạn injection thô.
- Ticket routing config nằm trong source, độc lập working directory; hỗ trợ personal-data reason và ưu tiên rule nghiêm trọng nhất.
- Chuẩn hóa role `EMPLOYEE`, `HR_ADMIN`, `SUPER_ADMIN`; vẫn nhận token role lowercase cũ.
- Thêm RBAC server-side cho document, index và evaluation.
- Citation chỉ được mở bởi chủ conversation và vẫn kiểm tra confidentiality.
- Retry giữ `parent_chat_request_id`; duplicate worker không tạo message/ticket lần hai.
- Streaming SSE đã nối Agent → Backend → Frontend; có heartbeat, tiến trình thân thiện và polling fallback.
- Cập nhật bốn diagram theo code hiện tại; node nét đứt là Future.

## Chưa hoàn thành - Future

- Upload -> extract -> chunk -> embed -> ChromaDB; job hiện mới dừng ở `QUEUED`.
- Retrieval filter theo role/department ngay trong Agent.
- Durable queue/worker, idempotency, timeout recovery và rate limit.
- Public Ticket API, ticket dashboard, assignment, resolution và notification.
- Khôi phục active conversation ổn định trên FE.
- Monitoring, feedback, 2FA/SSO và citation metadata đầy đủ.

## Kiểm thử

- Backend: **70 passed**.
- Agent/RAG pipeline: **215 passed**.
- FE Next.js: lint, typecheck và build đã pass.

## Tài liệu liên quan

- `docs/project/API/APIdoc.md`: contract BE - FE.
- `docs/rag-pipeline/AGENT_API.md`: contract Agent.
- `docs/project/diagrams/agent_flow_diagram.mermaid`: Agent flow.
- `docs/project/diagrams/deployment_diagram.mermaid`: deployment.
- `docs/project/diagrams/system_overview_diagram.mermaid`: system overview.
- `docs/project/diagrams/workflow.mmd`: workflow end-to-end.
