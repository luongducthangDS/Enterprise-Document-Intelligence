### 0. Quy ước chung
- Header: `Content-Type: application/json`, `Authorization: Bearer {token}` (cơ chế auth TBD).
- POST tạo tác vụ → gửi `Idempotency-Key`; retry mạng dùng lại key cũ, thao tác mới dùng key mới.
- Mọi response (thành công/thất bại) đều wrap: `request_id`, `success`, `data`, `error`, `meta`.
- Danh sách rỗng → `[]`; field chưa có giá trị → `null`.
- Job async lỗi vẫn trả HTTP 200, lỗi xử lý nằm trong `data.failure`.
- `meta` có thể có thêm `pagination`, `poll_after_ms`... FE không được phụ thuộc field `meta` chưa document.

**Response thành công (mẫu chung)**
```json
{
  "request_id": "req_01",
  "success": true,
  "data": {},
  "error": null,
  "meta": { "timestamp": "2026-08-05T08:30:00Z", "api_version": "v1" }
}
```

**Response thất bại (mẫu chung)**
```json
{
  "request_id": "req_01",
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Dữ liệu không hợp lệ.",
    "details": [{ "field": "question", "message": "Question không được để trống." }],
    "retryable": false,
    "retry_after_ms": null
  },
  "meta": { "timestamp": "2026-08-05T08:30:00Z", "api_version": "v1" }
}
```

---

### 1. Conversation API

**POST /conversations** — Tạo cuộc hội thoại mới
- Request: `{ "title": null }`
- Response `data`: `{ "conversation_id": "conv_01", "state": "ACTIVE", "created_at": "..." }`
- Lỗi: `UNAUTHORIZED (401)`

**GET /conversations/{conversation_id}** — Lấy info phiên (FE dựng lại state khi reload)
- Response `data`: `{ "conversation_id", "title", "state", "created_at", "ended_at", "message_count", "last_message_at" }`
- Lỗi: `CONVERSATION_NOT_FOUND (404)`, `UNAUTHORIZED (401)`

**GET /conversations/{conversation_id}/messages** — Lấy lịch sử message
- Query params: `limit` (mặc định 20), `cursor`; sắp xếp tăng dần theo `created_at`.
- Response `data`: `{ "conversation_id", "messages": [ { message_id, role: USER/ASSISTANT, content, chat_request_id, answer_status?, citations?: [{citation_id,title,page,section,version,effective_date}], created_at } ], "pagination": { "limit", "next_cursor" } }`
- Lỗi: `CONVERSATION_NOT_FOUND (404)`, `UNAUTHORIZED (401)`

**POST /conversations/{conversation_id}/end** — Kết thúc phiên, xóa ngữ cảnh
- Response `data`: `{ "conversation_id", "state": "ENDED", "ended_at" }`
- Lỗi: `CONVERSATION_NOT_FOUND (404)`, `CONVERSATION_ENDED (409)`

---

### 2. Chat RAG API

**POST /chat/requests** — Gửi câu hỏi (trả 202, FE bắt đầu polling)
- Request: `{ "conversation_id": "conv_01", "question": "..." }`
- Response `data`: `{ "chat_request_id", "conversation_id", "state": "QUEUED", "poll_after_ms": 1000 }`
- Lỗi: `VALIDATION_ERROR (400)`, `CONVERSATION_NOT_FOUND (404)`, `RATE_LIMITED (429)`
- Lưu ý: `question` sau trim không rỗng; giới hạn đề xuất 2.000 ký tự (TBD).

**GET /chat/requests/{chat_request_id}** — Lấy trạng thái/kết quả trả lời
- Response `data` (COMPLETED):
```json
{
  "chat_request_id": "chatreq_01",
  "conversation_id": "conv_01",
  "user_message_id": "msg_u1",
  "assistant_message_id": "msg_a1",
  "state": "COMPLETED",
  "answer_status": "ANSWERED",
  "answer": "Nhân viên được hưởng 12 ngày phép năm...",
  "citations": [{ "citation_id": "cit_01", "title": "Chính sách nghỉ phép", "page": 5, "section": "Điều 3.1", "version": "2.0", "effective_date": "2026-01-01" }],
  "warnings": [],
  "clarification": null,
  "failure": null,
  "latency_ms": 2840
}
```
- State máy: `QUEUED → RETRIEVING → GENERATING → COMPLETED / REFUSED / CLARIFICATION_REQUIRED / FAILED`
- Lỗi: `CHAT_REQUEST_NOT_FOUND (404)`

**Warning contract** (`warnings`, `[]` nếu không có; severity `INFO/WARNING/BLOCKING`)
- `INCOMPLETE_DATA`: có thông tin liên quan nhưng thiếu điều kiện/thời điểm/đối tượng áp dụng.
- `CONFLICTING_SOURCES`: nhiều nguồn mâu thuẫn, không đủ căn cứ tự chọn.
- `UNCLEAR_SOURCE`: thiếu title/page/section/version/effective_date để kiểm chứng.
- `OUTDATED_OR_SUPERSEDED_SOURCE`: nguồn có vẻ cũ/superseded.
- Nếu `severity=BLOCKING` và thiếu bằng chứng → state phải là `REFUSED`/`CLARIFICATION_REQUIRED`, không được `COMPLETED`.
```json
[
  { "type": "CONFLICTING_SOURCES", "severity": "WARNING", "message": "Có hai chính sách nêu số ngày phép khác nhau; cần HR xác nhận.", "citation_ids": ["cit_01","cit_02"], "recommended_action": "VERIFY_WITH_HR" },
  { "type": "UNCLEAR_SOURCE", "severity": "INFO", "message": "Nguồn chưa có version hoặc ngày hiệu lực.", "citation_ids": ["cit_03"], "recommended_action": "CHECK_SOURCE_METADATA" }
]
```

**Biến thể: thiếu bằng chứng**
```json
{ "state": "REFUSED", "answer_status": "INSUFFICIENT_EVIDENCE", "answer": "Tôi chưa tìm thấy đủ thông tin trong tài liệu hiện có.", "citations": [] }
```

**Biến thể: cần làm rõ**
```json
{
  "state": "CLARIFICATION_REQUIRED",
  "answer_status": "CLARIFICATION_REQUIRED",
  "answer": null,
  "clarification": { "question": "Bạn hỏi cho nhân viên chính thức hay thử việc?", "options": ["Chính thức", "Thử việc"] }
}
```

**POST /chat/requests/{chat_request_id}/retry** — Thử lại request có `retryable=true`
- Request: `{ "reason": "USER_RETRY" }`
- Response `data`: `{ "chat_request_id": "chatreq_02", "parent_chat_request_id": "chatreq_01", "state": "QUEUED", "poll_after_ms": 1000 }`
- Lỗi: `REQUEST_NOT_RETRYABLE (409)`, `RETRY_LIMIT_REACHED (409)`

---

### 3. Citation API

**GET /citations/{citation_id}** — Mở đoạn trích để kiểm chứng
- Response `data`:
```json
{
  "citation_id": "cit_01",
  "document": { "document_id": "doc_01", "title": "Chính sách nghỉ phép", "version": "2.0", "effective_date": "2026-01-01", "status": "ACTIVE" },
  "location": { "page": 5, "section": "Điều 3.1", "chunk_id": "chk_01" },
  "excerpt": "Người lao động được hưởng...",
  "conflict_warning": false
}
```
- Lỗi: `DOCUMENT_ACCESS_DENIED (403)`, `CITATION_NOT_FOUND (404)`
- Lưu ý: `version`/`effective_date` không có trong nguồn → trả `null`, không tự suy đoán.

---

### 4. Document & Ingestion API

**POST /documents** — Upload PDF/DOCX/XLSX (nội dung máy đọc được)
- Request: `multipart/form-data` — `file=@...`, `metadata={"title","version","effective_date","status"}`
- Response `data`: `{ "document_id", "ingestion_job_id", "status": "UPLOADED" }`
- Lỗi: `FILE_TOO_LARGE (413)`, `UNSUPPORTED_FILE_TYPE (415)`, `FILE_NOT_MACHINE_READABLE (422)`
- Lưu ý: giới hạn đề xuất 25MB/file (TBD); OCR ngoài phạm vi MVP.

**GET /documents** — List tài liệu (admin/audit)
- Query params: `status`, `category`, `ingestion_state`, `indexed`, `limit`, `cursor`
- Response `data`: `{ "documents": [ { document_id, title, category, version, effective_date, status, ingestion_state, indexed, created_at } ] }`, kèm `meta.pagination`

**GET /documents/{document_id}** — Chi tiết tài liệu
- Response `data`: `{ document_id, title, category, version, effective_date, status, language, source_file, checksum, confidentiality, "ingestion": { job_id, state, chunk_count, last_ingested_at, error }, "index": { indexed, index_version } }`

**PATCH /documents/{document_id}/metadata** — Cập nhật metadata (chỉ admin/HR owner)
- Request: `{ "title", "category", "version", "effective_date", "status", "language", "confidentiality" }`
- Response `data`: `{ document_id, metadata_updated: true, requires_reindex: true, updated_at }`

**POST /documents/{document_id}/archive** — Archive mềm (không xóa vật lý MVP)
- Request: `{ "reason": "SUPERSEDED_BY_NEW_VERSION" }`
- Response `data`: `{ document_id, status: "ARCHIVED", requires_reindex: true, archived_at }`
- Lỗi (áp dụng chung nhóm update/archive): `DOCUMENT_NOT_FOUND (404)`, `FORBIDDEN (403)`, `DOCUMENT_METADATA_INVALID (422)`, `DOCUMENT_STATUS_CONFLICT (409)`

**GET /ingestion-jobs/{job_id}** — Theo dõi extract/chunk/embedding/index
- Response `data`: `{ job_id, document_id, state, stage: "CHUNKING", progress_percent, error, poll_after_ms }`
- State: `QUEUED, PROCESSING, COMPLETED, FAILED`
- Lỗi: `INGESTION_JOB_NOT_FOUND (404)`

---

### 5. Index API

**POST /indexes/rebuilds** — Tạo tác vụ tái lập chỉ mục
- Request: `{ "document_ids": ["doc_01","doc_02"], "strategy": "REPLACE" }`
- Response `data`: `{ job_id, state: "QUEUED", poll_after_ms: 2000 }`
- Lỗi: `INDEX_REBUILD_IN_PROGRESS (409)`, `DOCUMENT_NOT_READY (422)`

**GET /indexes/rebuilds/{job_id}** — Lấy trạng thái re-index
- Response `data`: `{ job_id, state: "COMPLETED", progress_percent: 100, active_index_version, error }`
- Lỗi: `INDEX_JOB_NOT_FOUND (404)`

---

### 6. Evaluation API

**POST /evaluation/runs** — Chạy bộ câu hỏi đánh giá
- Request: `{ "dataset_id": "evalset_hr_v1", "index_version": "idxver_...", "model_config_id": "modelcfg_01" }`
- Response `data`: `{ run_id, state: "QUEUED", poll_after_ms: 3000 }`
- Lỗi: `EVALUATION_DATASET_NOT_FOUND (404)`, `EVALUATION_RUN_CONFLICT (409)`

**GET /evaluation/runs/{run_id}** — Lấy tiến độ/kết quả
- Response `data`: `{ run_id, state: "COMPLETED", "metrics": { recall_at_5, answer_correctness, citation_coverage, citation_correctness, p95_latency_ms }, quality_gate: "PASSED" }`
- Lỗi: `EVALUATION_RUN_NOT_FOUND (404)`

---

### 7. Monitoring API

**GET /monitoring/requests/{request_id}** — Xem retrieval/latency (không PII)
- Response `data`: `{ observed_request_id, total_latency_ms, "retrieval": [{ chunk_id, document_id, score }], answer_status, pii_logged: false }`
- Lỗi: `FORBIDDEN (403)`, `REQUEST_LOG_NOT_FOUND (404)`

---

### 8. Feedback API

**POST /feedback** — Thumbs up/down cho câu trả lời
- Quy ước: `assistant_message_id` do BE sinh (khi có output `ANSWERED`/`REFUSED`/`CLARIFICATION_REQUIRED`); FE không tự sinh. Retry sinh `chat_request_id` + `assistant_message_id` mới, giữ `parent_chat_request_id` để audit.
- Request: `{ "assistant_message_id": "msg_a2", "rating": "DOWN", "reason_code": "INCORRECT", "comment": "Chưa đúng cho nhân viên thử việc." }`
- Response `data`: `{ feedback_id, assistant_message_id, rating, created_at }`
- Lỗi: `MESSAGE_NOT_FOUND (404)`, `FEEDBACK_INVALID (422)`
- Lưu ý: `rating`: `UP`/`DOWN`; `comment` tối đa 500 ký tự.

---

### 9. Mã lỗi chuẩn & xử lý FE

| Nhóm lỗi | HTTP | FE xử lý |
|---|---|---|
| VALIDATION_ERROR | 400/422 | Hiển thị lỗi tại field; không tự retry |
| UNAUTHORIZED / FORBIDDEN | 401/403 | Yêu cầu đăng nhập / báo không có quyền |
| `*_NOT_FOUND` | 404 | Báo tài nguyên không tồn tại |
| `*_CONFLICT` / NOT_RETRYABLE | 409 | Không tạo request trùng; hiển thị thông báo |
| FILE_TOO_LARGE | 413 | Yêu cầu chọn file nhỏ hơn |
| UNSUPPORTED_FILE_TYPE | 415 | Chỉ chấp nhận PDF/DOCX/XLSX |
| RATE_LIMITED | 429 | Chờ theo `Retry-After` rồi cho thử lại |
| RAG_SERVICE_UNAVAILABLE | 503 | Hiện nút Thử lại nếu `retryable=true` |
| UPSTREAM_TIMEOUT | 504 | Giữ câu hỏi, cho phép thử lại |
| INTERNAL_ERROR | 500 | Thông báo lỗi chung, không hiện chi tiết kỹ thuật |

### 10. State mapping cho giao diện (Chat RAG)

| State | UI hiển thị | Hành động |
|---|---|---|
| QUEUED | Đang chờ xử lý | Poll theo `poll_after_ms` |
| RETRIEVING | Đang tìm trong tài liệu | Tiếp tục poll |
| GENERATING | Đang tổng hợp câu trả lời | Tiếp tục poll |
| COMPLETED | Answer + citation | Cho mở nguồn và feedback |
| REFUSED | Không đủ bằng chứng | Không hiển thị như lỗi hệ thống |
| CLARIFICATION_REQUIRED | Câu hỏi làm rõ | Gửi lựa chọn thành query mới cùng phiên |
| FAILED | Lỗi dễ hiểu | Chỉ hiện Retry nếu `error.retryable=true` |

### 11. Các điểm cần chốt trước khi code
- Cơ chế authentication & role (RBAC theo phòng ban).
- Giới hạn `question` (đề xuất 2.000 ký tự) và dung lượng upload (đề xuất 25MB).
- TTL cho conversation, idempotency key, log.
- Polling (`poll_after_ms`) hay đổi sang SSE/streaming.
- Feedback: upsert hay lưu lịch sử.

---

### 12. Nhật ký triển khai chi tiết – Conversation API (Implemented)

> **Trạng thái:** ✅ Đã hoàn thiện code, tích hợp Async PostgreSQL, bọc Standard Response Wrapper và vượt qua 100% Pytest suite.

#### 12.1. Danh sách Endpoints đã triển khai (`/api/v1/conversations`)

| Method | Endpoint | Mô tả | Authorization | Success HTTP | Error Codes |
|---|---|---|---|---|---|
| `POST` | `/api/v1/conversations` | Tạo cuộc hội thoại mới | Bearer JWT | `201 Created` | `UNAUTHORIZED (401)`, `VALIDATION_ERROR (422)` |
| `GET` | `/api/v1/conversations/{conversation_id}` | Lấy thông tin chi tiết & trạng thái cuộc hội thoại | Bearer JWT | `200 OK` | `UNAUTHORIZED (401)`, `FORBIDDEN (403)`, `CONVERSATION_NOT_FOUND (404)` |
| `GET` | `/api/v1/conversations/{conversation_id}/messages` | Lấy lịch sử tin nhắn của phiên (Cursor pagination) | Bearer JWT | `200 OK` | `UNAUTHORIZED (401)`, `FORBIDDEN (403)`, `CONVERSATION_NOT_FOUND (404)` |
| `POST` | `/api/v1/conversations/{conversation_id}/end` | Kết thúc phiên hội thoại (chuyển state = `ENDED`) | Bearer JWT | `200 OK` | `UNAUTHORIZED (401)`, `FORBIDDEN (403)`, `CONVERSATION_NOT_FOUND (404)`, `CONVERSATION_ENDED (409)` |

#### 12.2. Mô tả Request / Response mẫu

##### 1. Tạo cuộc hội thoại (`POST /api/v1/conversations`)
- **Request Body:**
  ```json
  {
    "title": "Hỏi về chế độ nghỉ phép năm"
  }
  ```
  *(Nếu `title` bằng `null` hoặc rỗng, hệ thống tự động đặt tên mặc định `"Hội thoại mới"`)*.
- **Response Success (201 Created):**
  ```json
  {
    "request_id": "req_a1b2c3d4e5f6",
    "success": true,
    "data": {
      "conversation_id": "11111111-1111-1111-1111-111111111111",
      "state": "ACTIVE",
      "title": "Hỏi về chế độ nghỉ phép năm",
      "created_at": "2026-08-06T04:30:00.000000+00:00"
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T04:30:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 2. Lấy thông tin phiên (`GET /api/v1/conversations/{conversation_id}`)
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_a1b2c3d4e5f6",
    "success": true,
    "data": {
      "conversation_id": "11111111-1111-1111-1111-111111111111",
      "title": "Hỏi về chế độ nghỉ phép năm",
      "state": "ACTIVE",
      "created_at": "2026-08-06T04:30:00.000000+00:00",
      "ended_at": null,
      "message_count": 2,
      "last_message_at": "2026-08-06T04:31:00.000000+00:00"
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T04:31:05.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 3. Lấy danh sách tin nhắn (`GET /api/v1/conversations/{conversation_id}/messages`)
- **Query Parameters:** `limit` (mặc định 20, max 100), `cursor` (tùy chọn).
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_a1b2c3d4e5f6",
    "success": true,
    "data": {
      "conversation_id": "11111111-1111-1111-1111-111111111111",
      "messages": [
        {
          "message_id": "msg_01",
          "role": "USER",
          "content": "Quy định nghỉ phép năm như thế nào?",
          "chat_request_id": null,
          "answer_status": null,
          "citations": null,
          "created_at": "2026-08-06T04:30:30.000000+00:00"
        },
        {
          "message_id": "msg_02",
          "role": "ASSISTANT",
          "content": "Theo quy định, nhân viên được hưởng 12 ngày phép năm...",
          "chat_request_id": "chatreq_01",
          "answer_status": "ANSWERED",
          "citations": [
            {
              "citation_id": "cit_01",
              "title": "Chính sách nghỉ phép 2026",
              "page": 5,
              "section": "Điều 3.1",
              "version": "2.0",
              "effective_date": "2026-01-01"
            }
          ],
          "created_at": "2026-08-06T04:31:00.000000+00:00"
        }
      ]
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T04:31:10.000000+00:00",
      "api_version": "v1",
      "pagination": {
        "limit": 20,
        "next_cursor": null
      }
    }
  }
  ```

##### 4. Kết thúc phiên hội thoại (`POST /api/v1/conversations/{conversation_id}/end`)
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_a1b2c3d4e5f6",
    "success": true,
    "data": {
      "conversation_id": "11111111-1111-1111-1111-111111111111",
      "state": "ENDED",
      "ended_at": "2026-08-06T04:32:00.000000+00:00"
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T04:32:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi kết thúc lại phiên đã ngắt (`409 Conflict`):**
  ```json
  {
    "request_id": "req_a1b2c3d4e5f6",
    "success": false,
    "data": null,
    "error": {
      "code": "CONVERSATION_ENDED",
      "message": "Phiên hội thoại đã kết thúc trước đó",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-06T04:32:05.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

---

### 13. Nhật ký triển khai chi tiết – Chat RAG API (Implemented)

Nhóm **Chat RAG API** đã được triển khai hoàn chỉnh tại `/api/v1/chat`, tuân thủ mô hình xử lý bất đồng bộ (Async Queue & Polling), tích hợp Clean Architecture DTO/Service/Endpoint, lưu trữ trạng thái phiên làm việc trong CSDL `chat_requests`, và áp dụng bọc Standard Response Wrapper.

#### Danh sách Endpoints đã lập trình:

1. `POST /api/v1/chat/requests` — Gửi câu hỏi RAG mới (Trả về 202 Accepted, FE bắt đầu polling)
2. `GET /api/v1/chat/requests/{chat_request_id}` — Polling thông tin trạng thái & kết quả câu trả lời
3. `POST /api/v1/chat/requests/{chat_request_id}/retry` — Thử lại yêu cầu RAG bị thất bại/từ chối (Trả về 202 Accepted)

---

#### Chi tiết Payload Mẫu & Chuẩn Response Wrapper:

##### 1. Gửi câu hỏi mới (`POST /api/v1/chat/requests`)
- **Request Body:**
  ```json
  {
    "conversation_id": "33333333-3333-3333-3333-333333333333",
    "question": "Nghỉ phép thai sản bao nhiêu tháng?"
  }
  ```
- **Response Success (`202 Accepted`):**
  ```json
  {
    "request_id": "req_88a99b00c11d",
    "success": true,
    "data": {
      "chat_request_id": "55555555-5555-5555-5555-555555555555",
      "conversation_id": "33333333-3333-3333-3333-333333333333",
      "state": "QUEUED",
      "poll_after_ms": 1000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T05:00:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Lỗi khi câu hỏi rỗng hoặc vượt 2000 ký tự (`400 Bad Request`):** `code: "VALIDATION_ERROR"`
- **Lỗi khi gửi vào hội thoại đã đóng (`409 Conflict`):** `code: "CONVERSATION_ENDED"`

##### 2. Lấy trạng thái & câu trả lời RAG (`GET /api/v1/chat/requests/{chat_request_id}`)
- **Response COMPLETED (`200 OK`):**
  ```json
  {
    "request_id": "req_88a99b00c11e",
    "success": true,
    "data": {
      "chat_request_id": "55555555-5555-5555-5555-555555555555",
      "conversation_id": "33333333-3333-3333-3333-333333333333",
      "user_message_id": "u1111111-1111-1111-1111-111111111111",
      "assistant_message_id": "a2222222-2222-2222-2222-222222222222",
      "state": "COMPLETED",
      "answer_status": "ANSWERED",
      "answer": "Dựa trên tài liệu chính sách của phòng ban Engineering: Nhân viên được hưởng đầy đủ quyền lợi theo quy định hiện hành.",
      "citations": [
        {
          "citation_id": "cit_ab12cd",
          "title": "Chính sách nhân sự - Phòng Engineering",
          "page": 3,
          "section": "Điều 2.1",
          "version": "1.0",
          "effective_date": "2026-01-01"
        }
      ],
      "warnings": [],
      "clarification": null,
      "failure": null,
      "latency_ms": 280
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T05:00:01.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response REFUSED khi không đủ dữ liệu (`200 OK`):** `state: "REFUSED"`, `answer_status: "INSUFFICIENT_EVIDENCE"`, `answer: "Tôi chưa tìm thấy đủ thông tin trong tài liệu hiện có."`

##### 3. Thử lại yêu cầu Chat RAG (`POST /api/v1/chat/requests/{chat_request_id}/retry`)
- **Request Body (Optional):**
  ```json
  {
    "reason": "USER_RETRY"
  }
  ```
- **Response Success (`202 Accepted`):**
  ```json
  {
    "request_id": "req_88a99b00c11f",
    "success": true,
    "data": {
      "chat_request_id": "66666666-6666-6666-6666-666666666666",
      "parent_chat_request_id": "55555555-5555-5555-5555-555555555555",
      "state": "QUEUED",
      "poll_after_ms": 1000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T05:00:02.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Lỗi khi yêu cầu không hợp lệ để retry (`409 Conflict`):** `code: "REQUEST_NOT_RETRYABLE"`
- **Lỗi khi vượt quá 3 lần retry (`409 Conflict`):** `code: "RETRY_LIMIT_REACHED"`

---

### 14. Nhật ký triển khai chi tiết – Citation API (Implemented)

Nhóm **Citation API** đã được triển khai hoàn chỉnh tại `/api/v1/citations/{citation_id}`, cho phép ứng dụng Frontend mở chi tiết trích dẫn tài liệu để đối soát và kiểm chứng câu trả lời từ RAG engine, tự động truy vấn thông tin tài liệu nguồn trong CSDL `documents`, đồng thời kiểm soát phân quyền xem tài liệu mật (`RESTRICTED` / `CONFIDENTIAL`).

#### Danh sách Endpoints đã lập trình:

1. `GET /api/v1/citations/{citation_id}` — Lấy chi tiết thông tin trích dẫn, vị trí trong tài liệu (trang, mục, chunk ID) và kiểm soát quyền truy cập tài liệu.

---

#### Chi tiết Payload Mẫu & Chuẩn Response Wrapper:

##### 1. Mở đoạn trích để kiểm chứng (`GET /api/v1/citations/{citation_id}`)
- **Response Success (`200 OK`):**
  ```json
  {
    "request_id": "req_99b00c11d22e",
    "success": true,
    "data": {
      "citation_id": "cit_01",
      "document": {
        "document_id": "doc_01",
        "title": "Chính sách nghỉ phép",
        "version": "2.0",
        "effective_date": "2026-01-01",
        "status": "ACTIVE"
      },
      "location": {
        "page": 5,
        "section": "Điều 3.1",
        "chunk_id": "chk_01"
      },
      "excerpt": "Người lao động được hưởng chế độ nghỉ phép theo đúng quy định hiện hành...",
      "conflict_warning": false
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-06T05:25:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Lỗi không tìm thấy trích dẫn (`404 Not Found`):**
  ```json
  {
    "request_id": "req_99b00c11d22f",
    "success": false,
    "data": null,
    "error": {
      "code": "CITATION_NOT_FOUND",
      "message": "Không tìm thấy thông tin trích dẫn tài liệu.",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-06T05:25:05.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Lỗi từ chối truy cập tài liệu mật (`403 Forbidden`):**
  ```json
  {
    "request_id": "req_99b00c11d230",
    "success": false,
    "data": null,
    "error": {
      "code": "DOCUMENT_ACCESS_DENIED",
      "message": "Bạn không có quyền truy cập thông tin trích dẫn từ tài liệu này.",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-06T05:25:10.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

---

### 15. Nhật ký triển khai chi tiết – Document & Ingestion API (Implemented)

> **Trạng thái:** ✅ Đã hoàn thiện code, tích hợp ORM (`DocumentDB`, `IngestionJobDB`), bọc Standard Response Wrapper và đạt **100% Pytest suite pass (37/37 tests pass)**.

#### 15.1. Danh sách Endpoints đã triển khai (`/api/v1/documents` & `/api/v1/ingestion-jobs`)

| Method | Endpoint | Mô tả | Authorization | Success HTTP | Error Codes |
|---|---|---|---|---|---|
| `POST` | `/api/v1/documents` | Upload tài liệu chính sách mới (PDF, DOCX, XLSX) | Bearer JWT | `201 Created` | `FILE_TOO_LARGE (413)`, `UNSUPPORTED_FILE_TYPE (415)`, `FILE_NOT_MACHINE_READABLE (422)` |
| `GET` | `/api/v1/documents` | Danh sách tài liệu chính sách (có filter status, category, ingestion_state, indexed & phân trang) | Bearer JWT | `200 OK` | `UNAUTHORIZED (401)` |
| `GET` | `/api/v1/documents/{document_id}` | Xem chi tiết tài liệu, thông tin ingestion & vector index | Bearer JWT | `200 OK` | `DOCUMENT_NOT_FOUND (404)`, `DOCUMENT_ACCESS_DENIED (403)` |
| `PATCH` | `/api/v1/documents/{document_id}/metadata` | Cập nhật metadata tài liệu (chỉ dành cho HR Admin / Super Admin) | Bearer JWT | `200 OK` | `DOCUMENT_NOT_FOUND (404)`, `FORBIDDEN (403)` |
| `POST` | `/api/v1/documents/{document_id}/archive` | Lưu trữ mềm (soft archive) tài liệu | Bearer JWT | `200 OK` | `DOCUMENT_NOT_FOUND (404)`, `FORBIDDEN (403)`, `DOCUMENT_STATUS_CONFLICT (409)` |
| `GET` | `/api/v1/ingestion-jobs/{job_id}` | Theo dõi trạng thái & tiến độ tác vụ xử lý trích xuất / chunking / index | Bearer JWT | `200 OK` | `INGESTION_JOB_NOT_FOUND (404)` |

#### 15.2. Mô tả Request / Response mẫu

##### 1. Upload tài liệu chính sách (`POST /api/v1/documents`)
- **Request Body:** `multipart/form-data`
  - `file`: `@chinh_sach_nghi_phep.pdf`
  - `title`: `"Chính sách nghỉ phép 2026"`
  - `category`: `"HR_POLICY"`
  - `version`: `"1.0"`
  - `effective_date`: `"2026-01-01"`
  - `confidentiality`: `"INTERNAL"`
- **Response Success (201 Created):**
  ```json
  {
    "request_id": "req_112233445566",
    "success": true,
    "data": {
      "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "ingestion_job_id": "j1j2j3j4-j5j6-7890-abcd-ef1234567890",
      "status": "ACTIVE"
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T09:40:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 2. Danh sách tài liệu (`GET /api/v1/documents`)
- **Query Parameters:** `status=ACTIVE&limit=20`
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_112233445567",
    "success": true,
    "data": [
      {
        "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "title": "Chính sách nghỉ phép 2026",
        "category": "HR_POLICY",
        "version": "1.0",
        "effective_date": "2026-01-01",
        "status": "ACTIVE",
        "ingestion_state": "QUEUED",
        "indexed": false,
        "created_at": "2026-08-07T09:40:00.000000+00:00"
      }
    ],
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T09:40:05.000000+00:00",
      "api_version": "v1",
      "pagination": {
        "limit": 20,
        "next_cursor": null
      }
    }
  }
  ```

##### 3. Chi tiết tài liệu (`GET /api/v1/documents/{document_id}`)
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_112233445568",
    "success": true,
    "data": {
      "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Chính sách nghỉ phép 2026",
      "category": "HR_POLICY",
      "version": "1.0",
      "effective_date": "2026-01-01",
      "status": "ACTIVE",
      "language": "vi",
      "source_file": "chinh_sach_nghi_phep.pdf",
      "checksum": "e3b0c44298fc1c14",
      "confidentiality": "INTERNAL",
      "ingestion": {
        "job_id": "j1j2j3j4-j5j6-7890-abcd-ef1234567890",
        "state": "QUEUED",
        "chunk_count": 0,
        "last_ingested_at": null,
        "error": null
      },
      "index": {
        "indexed": false,
        "index_version": null
      }
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T09:40:10.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 4. Cập nhật metadata (`PATCH /api/v1/documents/{document_id}/metadata`)
- **Request Body:**
  ```json
  {
    "title": "Chính sách nghỉ phép năm 2026 (Điều chỉnh)",
    "category": "BENEFITS",
    "version": "1.1"
  }
  ```
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_112233445569",
    "success": true,
    "data": {
      "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "metadata_updated": true,
      "requires_reindex": true,
      "updated_at": "2026-08-07T09:41:00.000000+00:00"
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T09:41:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 5. Soft Archive tài liệu (`POST /api/v1/documents/{document_id}/archive`)
- **Request Body:**
  ```json
  {
    "reason": "Superseded by version 2.0"
  }
  ```
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_112233445570",
    "success": true,
    "data": {
      "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "ARCHIVED",
      "requires_reindex": true,
      "archived_at": "2026-08-07T09:42:00.000000+00:00"
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T09:42:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 6. Theo dõi Ingestion Job (`GET /api/v1/ingestion-jobs/{job_id}`)
- **Response Success (200 OK):**
  ```json
  {
    "request_id": "req_112233445571",
    "success": true,
    "data": {
      "job_id": "j1j2j3j4-j5j6-7890-abcd-ef1234567890",
      "document_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "state": "QUEUED",
      "stage": "UPLOADED",
      "progress_percent": 0,
      "error": null,
      "poll_after_ms": 1000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T09:42:05.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

---

### 16. Nhật ký triển khai chi tiết – Index API (Implemented)

> **Trạng thái:** ✅ Đã hoàn thiện code, tích hợp ORM (`IndexJobDB`), bọc Standard Response Wrapper và đạt **100% Pytest suite pass (42/42 tests pass)**.

#### 16.1. Danh sách Endpoints đã triển khai (`/api/v1/indexes`)

| Method | Endpoint | Mô tả | Authorization | Success HTTP | Error Codes |
|---|---|---|---|---|---|
| `POST` | `/api/v1/indexes/rebuilds` | Tạo tác vụ tái lập chỉ mục (Re-index vector store) | Bearer JWT | `202 Accepted` | `INDEX_REBUILD_IN_PROGRESS (409)`, `DOCUMENT_NOT_READY (422)` |
| `GET` | `/api/v1/indexes/rebuilds/{job_id}` | Theo dõi trạng thái & tiến độ tái lập chỉ mục | Bearer JWT | `200 OK` | `INDEX_JOB_NOT_FOUND (404)` |

#### 16.2. Mô tả Request / Response mẫu

##### 1. Tạo tác vụ tái lập chỉ mục (`POST /api/v1/indexes/rebuilds`)
- **Request Body:**
  ```json
  {
    "document_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    "strategy": "REPLACE"
  }
  ```
  *(Nếu `document_ids` bằng `null`, hệ thống tự động rebuild cho tất cả các tài liệu đang ACTIVE trong hệ thống)*.
- **Response Success (`202 Accepted`):**
  ```json
  {
    "request_id": "req_223344556677",
    "success": true,
    "data": {
      "job_id": "idxjob_77889900aabb",
      "state": "QUEUED",
      "poll_after_ms": 2000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T10:05:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi có tác vụ re-index đang chạy (`409 Conflict`):**
  ```json
  {
    "request_id": "req_223344556678",
    "success": false,
    "data": null,
    "error": {
      "code": "INDEX_REBUILD_IN_PROGRESS",
      "message": "Đang có tác vụ tái lập chỉ mục đang thực thi. Vui lòng chờ hoàn tất.",
      "details": null,
      "retryable": true,
      "retry_after_ms": 2000
    },
    "meta": {
      "timestamp": "2026-08-07T10:05:05.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi tài liệu chỉ định chưa sẵn sàng / bị archive (`422 Unprocessable Entity`):**
  ```json
  {
    "request_id": "req_223344556679",
    "success": false,
    "data": null,
    "error": {
      "code": "DOCUMENT_NOT_READY",
      "message": "Tài liệu '44444444-4444-4444-4444-444444444444' không tồn tại hoặc ở trạng thái không thể index.",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-07T10:05:10.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 2. Lấy trạng thái Re-index (`GET /api/v1/indexes/rebuilds/{job_id}`)
- **Response Success (`200 OK`):**
  ```json
  {
    "request_id": "req_223344556680",
    "success": true,
    "data": {
      "job_id": "idxjob_77889900aabb",
      "state": "QUEUED",
      "stage": "QUEUED",
      "progress_percent": 0,
      "active_index_version": "v1.0",
      "error": null,
      "poll_after_ms": 2000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T10:05:15.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi không tìm thấy Job (`404 Not Found`):**
  ```json
  {
    "request_id": "req_223344556681",
    "success": false,
    "data": null,
    "error": {
      "code": "INDEX_JOB_NOT_FOUND",
      "message": "Không tìm thấy thông tin tác vụ tái lập chỉ mục.",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-07T10:05:20.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

---

### 17. Nhật ký triển khai chi tiết – Evaluation API (Implemented)

> **Trạng thái:** ✅ Đã hoàn thiện code, tích hợp ORM (`EvaluationRunDB`), bọc Standard Response Wrapper và đạt **100% Pytest suite pass (47/47 tests pass)**.

#### 17.1. Danh sách Endpoints đã triển khai (`/api/v1/evaluation`)

| Method | Endpoint | Mô tả | Authorization | Success HTTP | Error Codes |
|---|---|---|---|---|---|
| `POST` | `/api/v1/evaluation/runs` | Tạo tác vụ chạy đánh giá chất lượng bộ câu hỏi RAG (Evaluation Run) | Bearer JWT | `202 Accepted` | `EVALUATION_DATASET_NOT_FOUND (404)`, `EVALUATION_RUN_CONFLICT (409)` |
| `GET` | `/api/v1/evaluation/runs/{run_id}` | Theo dõi tiến độ & kết quả các chỉ số đánh giá RAG | Bearer JWT | `200 OK` | `EVALUATION_RUN_NOT_FOUND (404)` |

#### 17.2. Mô tả Request / Response mẫu

##### 1. Tạo tác vụ đánh giá (`POST /api/v1/evaluation/runs`)
- **Request Body:**
  ```json
  {
    "dataset_id": "evalset_hr_v1",
    "index_version": "idxver_v1.0",
    "model_config_id": "modelcfg_gpt4o"
  }
  ```
- **Response Success (`202 Accepted`):**
  ```json
  {
    "request_id": "req_334455667788",
    "success": true,
    "data": {
      "run_id": "evalrun_112233445566",
      "state": "QUEUED",
      "poll_after_ms": 3000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T10:50:00.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi bộ dữ liệu đánh giá không tồn tại (`404 Not Found`):**
  ```json
  {
    "request_id": "req_334455667789",
    "success": false,
    "data": null,
    "error": {
      "code": "EVALUATION_DATASET_NOT_FOUND",
      "message": "Không tìm thấy bộ dữ liệu đánh giá chỉ định.",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-07T10:50:05.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi có đợt đánh giá khác đang chạy (`409 Conflict`):**
  ```json
  {
    "request_id": "req_334455667790",
    "success": false,
    "data": null,
    "error": {
      "code": "EVALUATION_RUN_CONFLICT",
      "message": "Đang có đợt đánh giá chất lượng RAG đang thực thi. Vui lòng chờ hoàn tất.",
      "details": null,
      "retryable": true,
      "retry_after_ms": 3000
    },
    "meta": {
      "timestamp": "2026-08-07T10:50:10.000000+00:00",
      "api_version": "v1"
    }
  }
  ```

##### 2. Xem tiến độ & chỉ số đánh giá (`GET /api/v1/evaluation/runs/{run_id}`)
- **Response Success (`200 OK`):**
  ```json
  {
    "request_id": "req_334455667791",
    "success": true,
    "data": {
      "run_id": "evalrun_112233445566",
      "dataset_id": "evalset_hr_v1",
      "state": "COMPLETED",
      "stage": "COMPLETED",
      "progress_percent": 100,
      "metrics": {
        "recall_at_5": 0.92,
        "answer_correctness": 0.88,
        "citation_coverage": 0.95,
        "citation_correctness": 0.90,
        "p95_latency_ms": 1450
      },
      "quality_gate": "PASSED",
      "error": null,
      "poll_after_ms": 3000
    },
    "error": null,
    "meta": {
      "timestamp": "2026-08-07T10:50:15.000000+00:00",
      "api_version": "v1"
    }
  }
  ```
- **Response Error khi không tìm thấy Run (`404 Not Found`):**
  ```json
  {
    "request_id": "req_334455667792",
    "success": false,
    "data": null,
    "error": {
      "code": "EVALUATION_RUN_NOT_FOUND",
      "message": "Không tìm thấy thông tin lượt đánh giá.",
      "details": null,
      "retryable": false,
      "retry_after_ms": null
    },
    "meta": {
      "timestamp": "2026-08-07T10:50:20.000000+00:00",
      "api_version": "v1"
    }
  }
  ```