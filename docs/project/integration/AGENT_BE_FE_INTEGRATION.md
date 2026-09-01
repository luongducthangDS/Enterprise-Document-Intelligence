# Tích hợp Frontend – Backend – Agent

**Baseline:** `develop@87a85aa`
**Ngày đối chiếu:** 2026-09-01

## Ranh giới service

```text
Next.js Frontend
  └─ JWT REST/SSE ─> FastAPI Backend
                       ├─ PostgreSQL/Supabase
                       ├─ Cloudinary hoặc public document URL
                       └─ service token + signed identity ─> FastAPI Agent
                                                            ├─ LangGraph
                                                            ├─ Chroma
                                                            └─ OpenAI hoặc FPT-compatible gateway
```

- Frontend không gọi trực tiếp Agent và không tự quyết định quyền.
- Backend sở hữu authentication, RBAC, conversation, message, ticket, document, review, job và audit persistence.
- Agent stateless đối với nghiệp vụ; nhận identity đã ký, truy xuất nguồn được phép và trả kết quả/job state.

## Role và phạm vi

| Role | Quyền chính |
|---|---|
| `EMPLOYEE` | Chat, citation, conversation và ticket thuộc phạm vi được phép |
| `DEPARTMENT_MANAGER` | Quyền Employee và quản lý ticket/tài liệu trong phòng ban |
| `SUPER_ADMIN` | Quản trị liên phòng ban, access, audit, index và evaluation |

Mọi role/department/scope không hợp lệ phải fail closed. Tên cũ `HR_ADMIN` chỉ có thể xuất hiện trong tài liệu lịch sử, không phải contract hiện hành.

## Luồng chat

```text
FE POST /api/v1/chat/requests/stream
  → BE xác thực JWT và lấy identity từ database
  → BE lưu message/request, lấy history gần nhất
  → BE ký identity và stream POST /api/v1/agent/query/stream
  → Agent condense + route + ACL retrieval + grounded generation
  → Agent phát progress/answer_delta/result
  → BE lọc/mapping, persist answer/citation/ticket
  → FE hiển thị kết quả; polling status nếu SSE bị ngắt
```

Trạng thái chính: `QUEUED`/`GENERATING` → `COMPLETED`, `REFUSED` hoặc `FAILED`. Retry tạo request có liên kết với request cha và không được tạo trùng message/ticket.

## Luồng tài liệu

```text
Manager/Admin upload file hoặc URL
  → Backend tạo submission
  → Agent document-analysis worker extract/chunk/structure
  → Backend hiển thị kết quả để HITL review
  → approve tạo document/version
  → ingestion/index worker vô hiệu chunks phiên bản cũ và upsert bản mới
  → citation viewer mở đúng version/location
```

Backend hỗ trợ upload PDF, DOCX, XLSX, Markdown và image theo validation hiện hành. Tài liệu chỉ được đưa vào corpus chính sau khi qua review/approve.

## Internal Agent API

| Endpoint | Mục đích |
|---|---|
| `POST /api/v1/agent/query` | Query đồng bộ |
| `POST /api/v1/agent/query/stream` | Query streaming SSE |
| `POST /api/v1/agent/jobs/ingestion` | Ingestion/index tài liệu |
| `POST /api/v1/agent/jobs/document-analysis` | Phân tích submission |
| `POST /api/v1/agent/jobs/index-rebuild` | Rebuild index |
| `POST /api/v1/agent/jobs/evaluation` | Chạy evaluation |
| `GET /api/v1/agent/jobs/{job_id}` | Poll job state |

## Bảo mật tích hợp

1. Không tin role/department do browser tự gửi.
2. Backend gọi Agent bằng service token và signed identity có thời hạn.
3. Retrieval lọc tenant, role, department, scope và lifecycle trước generation, sau đó kiểm tra lại metadata.
4. Response/citation được lọc PII và kiểm tra quyền trước khi trả về Frontend.
5. Log/audit không chứa secret hoặc nguyên văn prompt injection nhạy cảm.

## Trạng thái xác minh

- Backend test tại baseline: **152 passed**.
- Agent/core: **589 passed, 44 skipped, 6 failed, 8 errors**; 12 lỗi phụ thuộc network/cloud và 2 lỗi cô lập cấu hình LLM.
- Frontend chưa được chạy lại tại phiên rà soát do không cài được dependency trong môi trường mạng hiện tại.

Chi tiết và lệnh tái lập: [`../../TESTING.md`](../../TESTING.md).
