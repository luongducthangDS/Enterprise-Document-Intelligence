# Agent Worker Contract (ingestion / index rebuild / evaluation)

Contract nội bộ Backend ↔ Agent cho 3 job admin. Xử lý finding #5/#6/#7 của
`bug_1308.md`: API tạo job nhưng không có worker nào chạy nên job kẹt `QUEUED`.

## Ranh giới sở hữu

| Việc | Chủ sở hữu |
|---|---|
| Bảng job (`ingestion_jobs`, `index_jobs`, `evaluation_runs`), API cho FE, phân quyền admin | Backend |
| Quyết định retry, chống trùng job, lưu metrics vào DB | Backend |
| Parse / chunk / embed / vector DB / chạy eval / chấm điểm | Agent |
| Trạng thái thực thi của một lần chạy (stage, progress, error) | Agent |

Agent **không** đọc/ghi DB của Backend và **không** tự retry. Agent chỉ chạy
đúng cái được giao rồi báo trạng thái; retry là quyết định của Backend vì bản ghi
job thật nằm ở đó.

## Luồng chuẩn

1. Backend tạo job trong DB (`QUEUED`) như hiện tại.
2. Backend `POST` sang agent kèm **chính `job_id` của Backend** → agent trả `202`.
3. Backend poll `GET /api/v1/agent/jobs/{job_id}` và mirror `state`/`stage`/
   `progress_percent`/`error` vào bảng job của mình (FE đã có sẵn UI polling).
4. Khi agent trả `COMPLETED`, Backend đọc `result` để ghi số liệu
   (`chunk_count`, `metrics`, `quality_gate`, ...).

Mọi endpoint đều yêu cầu header `X-Service-Token` giống `/agent/query`.

## Trạng thái job

| state | Ý nghĩa |
|---|---|
| `QUEUED` | Agent đã nhận, đang chờ tới lượt (job cùng loại chạy tuần tự) |
| `PROCESSING` | Đang chạy |
| `COMPLETED` | Xong, có `result` |
| `FAILED` | Hỏng, có `error` |

`stage` là nhãn tiến trình để hiển thị: `STARTED`, `EXTRACTING`, `CHUNKING`,
`EMBEDDING`, `INDEXING`, `PREPARING`, `LOADING_DATASET`, `RUNNING`, `SCORING`,
`COMPLETED`, `FAILED`.

Trạng thái được ghi ra đĩa (`AGENT_JOBS_DIR`), không giữ trong RAM. Nếu agent
restart giữa chừng, job dở dang bị đánh dấu `FAILED` với
`error = "AGENT_RESTARTED: ..."` ngay lúc startup — Backend luôn poll ra trạng
thái kết thúc thay vì chờ vô hạn. Backend thấy chuỗi `AGENT_RESTARTED` thì có thể
submit lại an toàn.

## Idempotency và retry

- Submit lại `job_id` đang `QUEUED`/`PROCESSING` → `409 Conflict`.
- Submit lại `job_id` đã `COMPLETED`/`FAILED` → chạy lại và ghi đè kết quả cũ.
- Job cùng loại chạy **tuần tự** trong agent (khoá theo loại job) để không có 2
  lần rebuild đụng cùng collection Chroma hoặc đốt song song hạn mức embedding.

## `POST /api/v1/agent/jobs/ingestion`

```jsonc
{
  "job_id": "e2b1...",            // id ingestion_jobs của Backend
  "document_id": "9f3c...",       // trace, agent trả lại nguyên văn
  "source_file": "quy_che_nghi_phep.pdf",  // quyết định chunk_id/source_stem
  "content_base64": "JVBERi0xLjQK...",     // nội dung file, tối đa 25MB sau decode
  "category": "LEAVE",
  "source_type": "official_policy",
  "is_official_policy": true,
  "caveat": ""
}
```

Chấp nhận `.pdf`, `.docx`, `.doc`, `.md`. PDF không có text layer sẽ đi đường VLM
(chậm hàng phút, tốn API) — `result.extract_method` cho biết đã đi đường nào.

`result` khi `COMPLETED`:

```jsonc
{
  "document_id": "9f3c...",
  "source_file": "quy_che_nghi_phep.pdf",
  "source_stem": "quy_che_nghi_phep",
  "extract_method": "text-layer",   // text-layer | vlm | docx | copy
  "char_count": 48213,
  "chunk_count": 42,
  "vector_count": 42,
  "chunks_path": "data/chunks/quy_che_nghi_phep.json",
  "processed_path": "data/processed/quy_che_nghi_phep.md",
  "collection": "hr_documents",
  "embedding_model": "multilingual-e5-large",
  "index_version": "v1.0"
}
```

Backend hiện gửi bytes upload dưới dạng base64 sang Agent ngay sau khi commit
`documents` + `ingestion_jobs`. Khi FE poll trạng thái, Backend mirror tiến độ và
lưu `chunk_count`/`processed_path`/`chunks_path`/thời điểm index từ kết quả Agent.

## `POST /api/v1/agent/jobs/index-rebuild`

```jsonc
{
  "job_id": "77aa...",
  "strategy": "REPLACE",          // REPLACE | FULL | INCREMENTAL
  "documents": [                   // rỗng = rebuild toàn bộ tài liệu đã có chunk
    {"document_id": "9f3c...", "source_file": "quy_che_nghi_phep.pdf"}
  ]
}
```

Rebuild chạy từ chunk đã lưu (`data/chunks/*.json`), **không** parse lại tài liệu.
Tài liệu chưa từng ingest sẽ làm job `FAILED` với thông báo nêu đích danh file
thiếu chunk. `REPLACE`/`FULL` xoá vector cũ trước khi upsert (dọn chunk mồ côi);
`INCREMENTAL` chỉ upsert đè.

`result`:

```jsonc
{
  "strategy": "REPLACE",
  "documents": [{"document_id": "9f3c...", "source_file": "...", "chunk_count": 42}],
  "document_count": 29,
  "vector_count": 1873,
  "collection": "hr_documents",
  "collection_count": 1873,
  "embedding_model": "multilingual-e5-large",
  "active_index_version": "v1.0"     // ghi vào index_jobs.active_index_version
}
```

## `POST /api/v1/agent/jobs/evaluation`

```jsonc
{
  "job_id": "5c10...",
  "dataset_id": "evalset_hr_v1",   // evalset_hr_v1 | evalset_default | evalset_hr_v2
  "limit": null,                    // chạy N câu đầu (smoke run)
  "concurrency": null,              // mặc định EVAL_CONCURRENCY
  "types": null                     // vd ["in_scope"]
}
```

`dataset_id` khớp `VALID_DATASETS` của Backend: `evalset_hr_v1`/`evalset_default`
→ `qa_eval_set.json` (dev set), `evalset_hr_v2` → `qa_heldout_set.json` (held-out).

`result`:

```jsonc
{
  "dataset_id": "evalset_hr_v1",
  "total": 100, "total_passed": 88, "error_count": 0,
  "summary_by_type": {"in_scope": {"passed": 52, "total": 60, "rate": 0.8667}},
  "metrics": {
    "retrieval_k": 10,
    "recall_at_k": 0.9167,
    "answer_correctness": 0.8833,
    "citation_coverage": 0.95,
    "citation_correctness": 0.90,
    "p50_latency_ms": 6120.4,
    "p95_latency_ms": 14210.9
  },
  "quality_gate": "PASSED",          // PASSED | FAILED | PENDING
  "quality_gate_details": [{"metric": "recall_at_k", "value": 0.9167, "threshold": 0.8, "passed": true}],
  "agent_model": "GLM-5.2", "judge_model": "Llama-3.3-70B-Instruct",
  "results": [/* chi tiết từng câu */]
}
```

Định nghĩa metric (giống `eval/scripts/eval_agent.py`, xem `src/evaluation/scoring.py`):

- `recall_at_k` — tỉ lệ câu `in_scope` mà retrieval lấy được đoạn gold. `k` là số
  chunk thực sự vào prompt (`rerank_top_k` khi bật reranker), trả kèm trong
  `retrieval_k`. Backend map giá trị này vào field `recall_at_5` của
  `EvaluationMetricsDTO` (tên field là di sản, hãy đọc kèm `retrieval_k`).
- `answer_correctness` — LLM-judge (model khác agent) xác nhận nội dung cốt lõi khớp.
- `citation_coverage` — tỉ lệ câu `in_scope` có ít nhất 1 citation.
- `citation_correctness` — tỉ lệ citation trỏ đúng đoạn gold, chỉ tính trên câu có nhãn gold.
- `quality_gate` — `PENDING` khi thiếu số liệu (vd toàn bộ case lỗi), tuyệt đối
  không quy ước thành `PASSED`. Ngưỡng cấu hình qua `EVAL_GATE_*`.

## Mã lỗi

| Tình huống | HTTP | Ghi chú |
|---|---|---|
| Thiếu/sai `X-Service-Token` | 401 | Áp dụng cho mọi route worker |
| Payload sai schema | 422 | Pydantic |
| `job_id` đang chạy | 409 | Backend không nên tự retry ngay, poll tiếp |
| Không tìm thấy job khi poll | 404 | Job chưa từng submit hoặc file trạng thái đã bị dọn |
| Lỗi khi chạy | 200 + `state=FAILED` | Lỗi nghiệp vụ nằm trong `error`, không phải HTTP error |
