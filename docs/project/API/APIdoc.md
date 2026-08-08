**API CONTRACT BE-FE**

# 1. Quy ước chung

- Header mặc định: Content-Type: application/json và Authorization: Bearer {token} (cơ chế auth sẽ chốt sau).
- POST tạo tác vụ nên gửi Idempotency-Key. Khi retry mạng, FE dùng lại cùng key; thao tác mới dùng key mới.
- Response luôn có request_id, success, data, error và meta.
- FE đọc state/answer_status để hiển thị UI; không đoán trạng thái từ nội dung answer.
- Danh sách rỗng trả []; field chưa có giá trị trả null.
## 1.1 Response format chuẩn

# Mọi response, kể cả thành công và thất bại, phải dùng cùng wrapper để FE xử lý thống nhất và BE trace log theo request_id.

# Response thành công
{
  "request_id": "req_01",
  "success": true,
  "data": {},
  "error": null,
  "meta": {
    "timestamp": "2026-08-05T08:30:00Z",
    "api_version": "v1"
  }
}

# Response thất bại
{
  "request_id": "req_01",
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Dữ liệu không hợp lệ.",
    "details": [
      {
        "field": "question",
        "message": "Question không được để trống."
      }
    ],
    "retryable": false,
    "retry_after_ms": null
  },
  "meta": {
    "timestamp": "2026-08-05T08:30:00Z",
    "api_version": "v1"
  }
}

# Quy ước: error là lỗi của HTTP/API call; với tác vụ async trả HTTP thành công nhưng job thất bại, đặt lỗi xử lý trong data.failure.

# meta có thể mở rộng với pagination, poll_after_ms, deprecation hoặc trace flags; FE không được phụ thuộc vào field meta chưa được document.

**Error response chuẩn**

```
{
  "request_id": "req_01",
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Dữ liệu không hợp lệ.",
    "retryable": false
  },
  "meta": {
    "timestamp": "2026-08-05T08:30:00Z",
    "api_version": "v1"
  }
}
```

# 2. Danh sách endpoint

| **Nhóm** | **Method và endpoint** | **Mục đích** |
| --- | --- | --- |
| **Conversation** | POST /conversations<br>GET /conversations/{id}<br>GET /conversations/{id}/messages<br>POST /conversations/{id}/end | Tạo phiên mới; lấy thông tin phiên; lấy lịch sử message; kết thúc/xóa ngữ cảnh phiên |
| **Chat RAG** | POST /chat/requests<br>GET /chat/requests/{id}<br>POST /chat/requests/{id}/retry | Gửi câu hỏi; lấy trạng thái/kết quả kèm message id/warnings; thử lại |
| **Citation** | GET /citations/{id} | Mở đoạn trích và metadata nguồn |
| **Document** | POST /documents<br>GET /documents<br>GET /documents/{id}<br>PATCH /documents/{id}/metadata<br>POST /documents/{id}/archive<br>GET /ingestion-jobs/{id} | Upload tài liệu; quản lý dataset/metadata; archive tài liệu; theo dõi ingest |
| **Index** | POST /indexes/rebuilds<br>GET /indexes/rebuilds/{id} | Tạo và theo dõi re-index |
| **Evaluation** | POST /evaluation/runs<br>GET /evaluation/runs/{id} | Chạy và xem kết quả đánh giá |
| **Monitoring** | GET /monitoring/requests/{request_id} | Xem retrieval/latency đã loại PII |
| **Feedback** | POST /feedback | Gửi thumbs up/down gắn với assistant_message_id |

# 3. Conversation API

## POST /conversations

Tạo cuộc hội thoại mới.

**Request**

```
{
  "title": null
}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "conversation_id": "conv_01",
    "state": "ACTIVE",
    "created_at": "2026-08-05T08:30:00Z"
  }
}
```

**Lỗi chính: **UNAUTHORIZED (401)

## GET /conversations/{conversation_id}

Lấy thông tin cuộc hội thoại để FE dựng lại trạng thái phiên khi reload hoặc mở lại màn hình chat.

Response thành công

{
  "success": true,
  "data": {
    "conversation_id": "conv_01",
    "title": null,
    "state": "ACTIVE",
    "created_at": "2026-08-05T08:30:00Z",
    "ended_at": null,
    "message_count": 2,
    "last_message_at": "2026-08-05T08:35:00Z"
  }
}

Lỗi chính: CONVERSATION_NOT_FOUND (404), UNAUTHORIZED (401)

## GET /conversations/{conversation_id}/messages

Lấy lịch sử message trong cuộc hội thoại, gồm message người dùng, assistant answer, trạng thái answer và citation tối thiểu để FE render lại chat panel.

Query params đề xuất: limit, cursor. Mặc định limit=20; sắp xếp tăng dần theo created_at.

Response thành công

{
  "success": true,
  "data": {
    "conversation_id": "conv_01",
    "messages": [
      {
        "message_id": "msg_u1",
        "role": "USER",
        "content": "Nhân viên có bao nhiêu ngày phép năm?",
        "chat_request_id": "chatreq_01",
        "created_at": "2026-08-05T08:34:00Z"
      },
      {
        "message_id": "msg_a1",
        "role": "ASSISTANT",
        "content": "Nhân viên được hưởng 12 ngày phép năm...",
        "chat_request_id": "chatreq_01",
        "answer_status": "ANSWERED",
        "citations": [
          {
            "citation_id": "cit_01",
            "title": "Chính sách nghỉ phép",
            "page": 5,
            "section": "Điều 3.1",
            "version": "2.0",
            "effective_date": "2026-01-01"
          }
        ],
        "created_at": "2026-08-05T08:35:00Z"
      }
    ],
    "pagination": {
      "limit": 20,
      "next_cursor": null
    }
  }
}

Lỗi chính: CONVERSATION_NOT_FOUND (404), UNAUTHORIZED (401)

## POST /conversations/{conversation_id}/end

Kết thúc phiên và xóa ngữ cảnh đang dùng cho lượt hỏi sau.

**Response thành công**

```
{
  "success": true,
  "data": {
    "conversation_id": "conv_01",
    "state": "ENDED",
    "ended_at": "2026-08-05T09:00:00Z"
  }
}
```

**Lỗi chính: **CONVERSATION_NOT_FOUND (404), CONVERSATION_ENDED (409)

# 4. Chat RAG API

## POST /chat/requests

Gửi câu hỏi. Trả 202 để FE bắt đầu polling.

**Request**

```
{
  "conversation_id": "conv_01",
  "question": "Nhân viên có bao nhiêu ngày phép năm?"
}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "chat_request_id": "chatreq_01",
    "conversation_id": "conv_01",
    "state": "QUEUED",
    "poll_after_ms": 1000
  }
}
```

**Lỗi chính: **VALIDATION_ERROR (400), CONVERSATION_NOT_FOUND (404), RATE_LIMITED (429)

**Lưu ý: **question sau trim không được rỗng; giới hạn đề xuất 2.000 ký tự (TBD).

## GET /chat/requests/{chat_request_id}

Lấy trạng thái và kết quả trả lời.

**Response thành công**

# {
  "request_id": "req_05",
  "success": true,
  "data": {
    "chat_request_id": "chatreq_01",
    "conversation_id": "conv_01",
    "user_message_id": "msg_u1",
    "assistant_message_id": "msg_a1",
    "state": "COMPLETED",
    "answer_status": "ANSWERED",
    "answer": "Nhân viên được hưởng 12 ngày phép năm...",
    "citations": [
      {
        "citation_id": "cit_01",
        "title": "Chính sách nghỉ phép",
        "page": 5,
        "section": "Điều 3.1",
        "version": "2.0",
        "effective_date": "2026-01-01"
      }
    ],
    "warnings": [],
    "clarification": null,
    "failure": null,
    "latency_ms": 2840
  },
  "error": null,
  "meta": {
    "timestamp": "2026-08-05T08:30:00Z",
    "api_version": "v1"
  }
}

**Lỗi chính: **CHAT_REQUEST_NOT_FOUND (404)

**Lưu ý: **State: QUEUED, RETRIEVING, GENERATING, COMPLETED, REFUSED, CLARIFICATION_REQUIRED, FAILED.

## Warning contract cho chat response

# warnings dùng để FE hiển thị cảnh báo nghiệp vụ mà không coi là lỗi hệ thống. Nếu không có cảnh báo trả [].

# Các type MVP:
- INCOMPLETE_DATA: tài liệu có thông tin liên quan nhưng thiếu điều kiện, thời điểm, đối tượng áp dụng hoặc metadata cần thiết.
- CONFLICTING_SOURCES: nhiều nguồn phù hợp nhưng nội dung mâu thuẫn và hệ thống không đủ căn cứ để tự chọn.
- UNCLEAR_SOURCE: có nội dung truy xuất được nhưng thiếu title/page/section/version/effective_date để kiểm chứng đầy đủ.
- OUTDATED_OR_SUPERSEDED_SOURCE: nguồn có vẻ cũ/superseded; chỉ dùng khi cần nêu mâu thuẫn hoặc không có nguồn active rõ hơn.

# Ví dụ warnings
[
  {
    "type": "CONFLICTING_SOURCES",
    "severity": "WARNING",
    "message": "Có hai chính sách nêu số ngày phép khác nhau; cần HR xác nhận nguồn áp dụng.",
    "citation_ids": ["cit_01", "cit_02"],
    "recommended_action": "VERIFY_WITH_HR"
  },
  {
    "type": "UNCLEAR_SOURCE",
    "severity": "INFO",
    "message": "Nguồn hỗ trợ câu trả lời chưa có version hoặc ngày hiệu lực.",
    "citation_ids": ["cit_03"],
    "recommended_action": "CHECK_SOURCE_METADATA"
  }
]

# Quy ước severity: INFO, WARNING, BLOCKING. Nếu severity=BLOCKING và không đủ bằng chứng, state nên là REFUSED hoặc CLARIFICATION_REQUIRED thay vì COMPLETED.

**Biến thể: thiếu bằng chứng**

```
{
  "state": "REFUSED",
  "answer_status": "INSUFFICIENT_EVIDENCE",
  "answer": "Tôi chưa tìm thấy đủ thông tin trong tài liệu hiện có.",
  "citations": []
}
```

**Biến thể: cần làm rõ**

```
{
  "state": "CLARIFICATION_REQUIRED",
  "answer_status": "CLARIFICATION_REQUIRED",
  "answer": null,
  "clarification": {
    "question": "Bạn hỏi cho nhân viên chính thức hay thử việc?",
    "options": [
      "Chính thức",
      "Thử việc"
    ]
  }
}
```

## POST /chat/requests/{chat_request_id}/retry

Thử lại request lỗi có retryable=true.

**Request**

```
{
  "reason": "USER_RETRY"
}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "chat_request_id": "chatreq_02",
    "parent_chat_request_id": "chatreq_01",
    "state": "QUEUED",
    "poll_after_ms": 1000
  }
}
```

**Lỗi chính: **REQUEST_NOT_RETRYABLE (409), RETRY_LIMIT_REACHED (409)

# 5. Citation API

## GET /citations/{citation_id}

Mở đoạn trích đủ ngữ cảnh để người dùng kiểm chứng.

**Response thành công**

```
{
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
    "excerpt": "Người lao động được hưởng...",
    "conflict_warning": false
  }
}
```

**Lỗi chính: **DOCUMENT_ACCESS_DENIED (403), CITATION_NOT_FOUND (404)

**Lưu ý: **version/effective_date không có trong nguồn thì trả null, không tự suy đoán.

# 6. Document và Ingestion API

## POST /documents

Upload PDF, DOCX hoặc XLSX có nội dung máy đọc được.

**Request**

```
Content-Type: multipart/form-data
file=@chinh_sach_nghi_phep_v2.pdf
metadata={"title":"Chính sách nghỉ phép","version":"2.0","effective_date":"2026-01-01","status":"ACTIVE"}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "document_id": "doc_01",
    "ingestion_job_id": "ing_01",
    "status": "UPLOADED"
  }
}
```

**Lỗi chính: **FILE_TOO_LARGE (413), UNSUPPORTED_FILE_TYPE (415), FILE_NOT_MACHINE_READABLE (422)

**Lưu ý: **Giới hạn dung lượng đề xuất 25 MB/file (TBD); OCR ngoài MVP.

## GET /documents

# Lấy danh sách tài liệu phục vụ admin/demo dataset, data audit và kiểm tra trạng thái ingest/index.

# Query params đề xuất: status, category, ingestion_state, indexed, limit, cursor.

# Response thành công
{
  "request_id": "req_20",
  "success": true,
  "data": {
    "documents": [
      {
        "document_id": "doc_01",
        "title": "Chính sách nghỉ phép",
        "category": "leave_policy",
        "version": "2.0",
        "effective_date": "2026-01-01",
        "status": "ACTIVE",
        "ingestion_state": "COMPLETED",
        "indexed": true,
        "created_at": "2026-08-05T08:30:00Z"
      }
    ]
  },
  "error": null,
  "meta": {
    "timestamp": "2026-08-05T08:30:00Z",
    "api_version": "v1",
    "pagination": {
      "limit": 20,
      "next_cursor": null
    }
  }
}

## GET /documents/{document_id}

# Lấy chi tiết tài liệu, metadata nguồn, trạng thái ingest/index, checksum và lỗi xử lý nếu có.

# Response thành công
{
  "request_id": "req_21",
  "success": true,
  "data": {
    "document_id": "doc_01",
    "title": "Chính sách nghỉ phép",
    "category": "leave_policy",
    "version": "2.0",
    "effective_date": "2026-01-01",
    "status": "ACTIVE",
    "language": "vi",
    "source_file": "chinh_sach_nghi_phep_v2.pdf",
    "checksum": "sha256:...",
    "confidentiality": "INTERNAL",
    "ingestion": {
      "job_id": "ing_01",
      "state": "COMPLETED",
      "chunk_count": 42,
      "last_ingested_at": "2026-08-05T08:40:00Z",
      "error": null
    },
    "index": {
      "indexed": true,
      "index_version": "idxver_20260805_01"
    }
  },
  "error": null,
  "meta": {
    "timestamp": "2026-08-05T08:40:00Z",
    "api_version": "v1"
  }
}

## PATCH /documents/{document_id}/metadata

# Cập nhật metadata dùng cho citation, ranking, active/superseded policy và demo dataset. Chỉ role admin/HR owner được dùng.

# Request
{
  "title": "Chính sách nghỉ phép",
  "category": "leave_policy",
  "version": "2.0",
  "effective_date": "2026-01-01",
  "status": "ACTIVE",
  "language": "vi",
  "confidentiality": "INTERNAL"
}

# Response thành công
{
  "request_id": "req_22",
  "success": true,
  "data": {
    "document_id": "doc_01",
    "metadata_updated": true,
    "requires_reindex": true,
    "updated_at": "2026-08-05T08:45:00Z"
  },
  "error": null,
  "meta": {
    "timestamp": "2026-08-05T08:45:00Z",
    "api_version": "v1"
  }
}

## POST /documents/{document_id}/archive

# Archive mềm tài liệu để loại khỏi index mặc định nhưng vẫn giữ audit trail cho citation/evaluation cũ. Không xóa vật lý trong MVP.

# Request
{
  "reason": "SUPERSEDED_BY_NEW_VERSION"
}

# Response thành công
{
  "request_id": "req_23",
  "success": true,
  "data": {
    "document_id": "doc_01",
    "status": "ARCHIVED",
    "requires_reindex": true,
    "archived_at": "2026-08-05T08:50:00Z"
  },
  "error": null,
  "meta": {
    "timestamp": "2026-08-05T08:50:00Z",
    "api_version": "v1"
  }
}

# Lỗi chính: DOCUMENT_NOT_FOUND (404), FORBIDDEN (403), DOCUMENT_METADATA_INVALID (422), DOCUMENT_STATUS_CONFLICT (409)

## GET /ingestion-jobs/{job_id}

Theo dõi extract, chunk, embedding và index.

**Response thành công**

```
{
  "success": true,
  "data": {
    "job_id": "ing_01",
    "document_id": "doc_01",
    "state": "PROCESSING",
    "stage": "CHUNKING",
    "progress_percent": 65,
    "error": null,
    "poll_after_ms": 1000
  }
}
```

**Lỗi chính: **INGESTION_JOB_NOT_FOUND (404)

**Lưu ý: **state: QUEUED, PROCESSING, COMPLETED, FAILED.

# 7. Index API

## POST /indexes/rebuilds

Tạo tác vụ tái lập chỉ mục.

**Request**

```
{
  "document_ids": [
    "doc_01",
    "doc_02"
  ],
  "strategy": "REPLACE"
}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "job_id": "idx_01",
    "state": "QUEUED",
    "poll_after_ms": 2000
  }
}
```

**Lỗi chính: **INDEX_REBUILD_IN_PROGRESS (409), DOCUMENT_NOT_READY (422)

## GET /indexes/rebuilds/{job_id}

Lấy trạng thái re-index.

**Response thành công**

```
{
  "success": true,
  "data": {
    "job_id": "idx_01",
    "state": "COMPLETED",
    "progress_percent": 100,
    "active_index_version": "idxver_20260805_01",
    "error": null
  }
}
```

**Lỗi chính: **INDEX_JOB_NOT_FOUND (404)

# 8. Evaluation API

## POST /evaluation/runs

Chạy bộ câu hỏi đánh giá theo index/model config.

**Request**

```
{
  "dataset_id": "evalset_hr_v1",
  "index_version": "idxver_20260805_01",
  "model_config_id": "modelcfg_01"
}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "run_id": "eval_01",
    "state": "QUEUED",
    "poll_after_ms": 3000
  }
}
```

**Lỗi chính: **EVALUATION_DATASET_NOT_FOUND (404), EVALUATION_RUN_CONFLICT (409)

## GET /evaluation/runs/{run_id}

Lấy tiến độ hoặc kết quả evaluation.

**Response thành công**

```
{
  "success": true,
  "data": {
    "run_id": "eval_01",
    "state": "COMPLETED",
    "metrics": {
      "recall_at_5": 0.87,
      "answer_correctness": 0.82,
      "citation_coverage": 0.96,
      "citation_correctness": 0.88,
      "p95_latency_ms": 7200
    },
    "quality_gate": "PASSED"
  }
}
```

**Lỗi chính: **EVALUATION_RUN_NOT_FOUND (404)

# 9. Monitoring API

## GET /monitoring/requests/{request_id}

Xem retrieval và latency; không trả PII/prompt nội bộ.

**Response thành công**

```
{
  "success": true,
  "data": {
    "observed_request_id": "req_05",
    "total_latency_ms": 2840,
    "retrieval": [
      {
        "chunk_id": "chk_01",
        "document_id": "doc_01",
        "score": 0.91
      }
    ],
    "answer_status": "ANSWERED",
    "pii_logged": false
  }
}
```

**Lỗi chính: **FORBIDDEN (403), REQUEST_LOG_NOT_FOUND (404)

# 10. Feedback API

## POST /feedback

## Quy ước assistant_message_id

# Feedback phải gắn với assistant_message_id do BE sinh và lưu ổn định. FE không tự sinh id này.

# BE tạo user_message_id khi nhận POST /chat/requests; tạo assistant_message_id khi có assistant output: ANSWERED, REFUSED hoặc CLARIFICATION_REQUIRED. Retry tạo chat_request_id và assistant_message_id mới, đồng thời giữ parent_chat_request_id để audit.

Gửi thumbs up/down cho câu trả lời.

**Request**

```
{
  "assistant_message_id": "msg_a2",
  "rating": "DOWN",
  "reason_code": "INCORRECT",
  "comment": "Chưa đúng cho nhân viên thử việc."
}
```

**Response thành công**

```
{
  "success": true,
  "data": {
    "feedback_id": "fb_01",
    "assistant_message_id": "msg_a2",
    "rating": "DOWN",
    "created_at": "2026-08-05T09:35:00Z"
  }
}
```

**Lỗi chính: **MESSAGE_NOT_FOUND (404), FEEDBACK_INVALID (422)

**Lưu ý: **rating: UP/DOWN; comment tối đa 500 ký tự.

# 11. Mã lỗi và xử lý phía FE

| **Nhóm lỗi** | **HTTP** | **FE xử lý** |
| --- | --- | --- |
| **VALIDATION_ERROR** | 400/422 | Hiển thị lỗi tại field; không retry tự động |
| **UNAUTHORIZED / FORBIDDEN** | 401/403 | Yêu cầu đăng nhập hoặc báo không có quyền |
| ***_NOT_FOUND** | 404 | Báo tài nguyên không tồn tại |
| ***_CONFLICT / NOT_RETRYABLE** | 409 | Không tạo request trùng; hiển thị thông báo |
| **FILE_TOO_LARGE** | 413 | Yêu cầu chọn file nhỏ hơn |
| **UNSUPPORTED_FILE_TYPE** | 415 | Chỉ chấp nhận PDF/DOCX/XLSX |
| **RATE_LIMITED** | 429 | Chờ theo Retry-After rồi cho phép thử lại |
| **RAG_SERVICE_UNAVAILABLE** | 503 | Hiện nút Thử lại nếu retryable=true |
| **UPSTREAM_TIMEOUT** | 504 | Giữ câu hỏi và cho phép thử lại |
| **INTERNAL_ERROR** | 500 | Thông báo lỗi chung; không hiển thị chi tiết kỹ thuật |

# 12. State mapping cho giao diện

| **State** | **UI hiển thị** | **Hành động** |
| --- | --- | --- |
| **QUEUED** | Đang chờ xử lý | Poll theo poll_after_ms |
| **RETRIEVING** | Đang tìm trong tài liệu | Tiếp tục poll |
| **GENERATING** | Đang tổng hợp câu trả lời | Tiếp tục poll |
| **COMPLETED** | Answer + citation | Cho mở nguồn và feedback |
| **REFUSED** | Không đủ bằng chứng | Không hiển thị như lỗi hệ thống |
| **CLARIFICATION_REQUIRED** | Câu hỏi làm rõ | Gửi lựa chọn thành query mới trong cùng phiên |
| **FAILED** | Lỗi dễ hiểu | Chỉ hiện Retry nếu error.retryable=true |

# 13. Các điểm nhóm cần chốt trước khi code

- Cơ chế authentication và role.
- Giới hạn question và dung lượng upload.
- TTL cho conversation, idempotency key và log.
- Polling như tài liệu hay đổi sang SSE/streaming.
- Quy tắc feedback: upsert hay lưu lịch sử.
