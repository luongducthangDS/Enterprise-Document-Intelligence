# PILOT READINESS IMPLEMENTATION PLAN — P-153 Doc Intelligence Agent

```text
Ngày lập plan:   2026-08-23
Nguồn证据:       Đọc trực tiếp source code (src/, backend/, frontend/, config/, supabase/),
                 git show commit 41263e9 (origin/develop), 4 báo cáo QC/remediation 22/08.
Base revision:   local develop @ 08487c4 — ĐANG TỤT SAU origin/develop 7 COMMIT
                 (bao gồm 41263e9: determinism fix + sync_document_titles + 9656bdb/94e9a48:
                 knowledge layer Supabase migration).
Nguyên tắc:      Mọi file:line dưới đây đã đối chiếu source. Không đoán architecture.
                 Ưu tiên source code khi mâu thuẫn tài liệu (xem mục 1.4 Discrepancies).
```

---

## 1. Current State

### 1.1 Điểm mạnh (giữ nguyên, không đụng)

- **Security đã hoàn thiện ở mức P0**: tenant isolation write/read path, ACL fail-closed 2 lớp (registry allowlist + runtime predicate, sentinel `__NO_ACCESS__`), HMAC identity, role reload từ DB mỗi request, DB trigger chống self-escalation, guardrail injection 2 lớp, PII redaction. Test inventory dày: E1–E6, F1–F3, H1–H3, tenant write isolation.
- **Hallucination control**: quyết định REFUSED đi qua marker `[KHÔNG_ĐỦ_THÔNG_TIN]` (generation.py:13) + confidence cap (escalation.py:228–251); 10/10 câu out-of-corpus abstain đúng.
- **Vòng đời ingestion backend↔worker ĐÃ HOẠT ĐỘNG E2E** (qua API): upload → job → extract → chunk → embed → Chroma tenant collection → citation, có P1a–P5 PASS live. Đây là phát hiện quan trọng nhất của đợt khảo sát này: **worker không hề "chưa triển khai"** — UI đang khóa bằng text stale (chi tiết 1.4).
- **Eval có kỷ luật**: 3 tầng router/retrieval/agent, held-out không tune, regression test khóa bug (test_bugfix_regression.py, test_live_ingestion.py).

### 1.2 Blockers (phải xử lý trước pilot)

| ID | Blocker | Bằng chứng code |
|---|---|---|
| B-1 | **Nondeterminism COMPLETED↔REFUSED**: rerank API lỗi → fail-open âm thầm → rơi vào nhánh distance fallback → REFUSED; rerank OK → COMPLETED. Cùng câu hỏi cho 2 kết quả trái ngược. | `src/agents/nodes/retrieval.py:354-356` (except → `return chunks[:rerank_top_k]`, score=None) → `retrieval.py:383-387` (grade rơi nhánh `distance <= 0.18`) → `escalation.py:215-251` (confidence = công thức distance → thường < 0.2 → escalate) |
| B-2 | **Citation attribution sai (BUG-05)**: prose LLM tự gọi tên tài liệu, citation object bind theo marker `[Nguồn N]` — nếu LLM đánh số lệch, answer nói doc A nhưng citation trỏ doc B. Grounding check dùng pool **toàn bộ** retrieved chunks nên mis-numbering VẪN PASS hallucination gate. Code tự thừa nhận lỗi này. | `generation.py:41` (prompt cho phép nêu tên policy trong prose), `:310` (context hiển thị title), `:419-440` (citation bind), `:466-473` (comment thừa nhận "đánh số citation lệch"), grounding pool = `state.get("retrieved_chunks")` |
| B-3 | **Metadata citation mất ở read-path**: version/effective_date/document_code CÓ trong Chroma metadata (corpus HR có front-matter đầy đủ) nhưng bị drop tại `_to_chunk`, thiếu field ở model Citation, adapter hardcode `None`. UI luôn hiện "Phiên bản — / Hiệu lực —". | `retrieval.py:181-209` (_to_chunk drop fields), `src/models/schemas.py:162-198` (model thiếu fields), `backend/app/services/agent_answer_adapter.py:84-85` (`"version": None, "effective_date": None`) |
| B-4 | **Admin portal khóa bằng stale text** dù backend + worker đầy đủ: upload/re-index/eval không dùng được từ UI, monitoring chưa có API. Persona Knowledge Admin gần như không usable. | `frontend/components/KnowledgeAdmin.tsx:57` ("Upload tạm khóa — worker chưa triển khai" — SAI), `:68-73` (OperationsView stale), `HrKnowledgeApp.tsx:79` (DeferredView "CHƯA NỐI API"); `frontend/lib/api.ts:336-361` đã có uploadDocument/getIngestionJob/startIndexRebuild/startEvaluation (+getIndexRebuild/getEvaluation) nhưng không component nào gọi |
| B-5 | **Over-refusal**: doc KPI/tuyển dụng có trong corpus nhưng REFUSED (E1, P3-Manager). Remote `41263e9` đã hạ `rerank_min_score` 0.05→0.01 + thêm query expansion KPI/tuyển dụng — chưa verify bằng eval. | `src/config.py:338` (0.05 local / 0.01 remote), `retrieval.py:385` (so sánh score >= rerank_min_score), `retrieval.py` remote: `_KPI_QUERY_PATTERN`, `_RECRUITMENT_QUERY_PATTERN` |
| B-6 | **2 credential đã lộ trong terminal** (Supabase DB password, Chroma API key) — rotation manual chưa làm; CI chưa có secret-scan; backend có JWT secret default yếu. | `backend/app/core/config.py:45` (`jwt_secret_key: str = "12345678900aaa"`), `.github/workflows/ci.yml` (chỉ ruff+pytest, không gitleaks) |

### 1.3 Risk matrix

| Risk | Severity | Probability | Ghi chú |
|---|---|---|---|
| Nhân viên nhận REFUSED sai do rerank gateway chập chờn | High | High | Đã xảy ra thực đo (DATA-01) |
| User tin nhầm nguồn do citation gán nhầm doc | High | Medium | Đã xảy ra 1 case thực đo (BUG-05) |
| Security regression khi sửa retrieval/citation | High | Low | Có regression suite khóa sẵn — phải chạy đủ |
| Tuning over-refusal làm tăng hallucination | Medium | Medium | Buộc chạy lại bộ adversarial + out-of-corpus sau mỗi đổi ngưỡng |
| Pull 7 commit remote gây conflict với workspace | Low | Low | Local clean, chỉ 1 file untracked; fast-forward được |
| Eval held-out bị tune trộm khi sửa ngưỡng | Medium | Medium | Chỉ tune trên dev split; held-out đóng băng |

### 1.4 Discrepancies (source code vs tài liệu — source thắng)

1. **"Worker chưa triển khai" (QC report, text UI) — SAI.** Worker ingestion/index-rebuild/evaluation tồn tại hoàn chỉnh: `src/workers/jobs.py` (JobStore asyncio + lock theo kind + persist JSON), `src/workers/ingestion.py:120-202`, `src/workers/indexing.py:105-167`, `src/workers/evaluation.py`; agent routes `src/api/routes.py:137-164`; E2E `tests/e2e/test_live_ingestion.py` P1a–d PASS live. Text khóa trong `KnowledgeAdmin.tsx:57,68-73` là stale.
2. **"Role DEPARTMENT_USER không tồn tại runtime" (E2E remediation report BUG-04) — CẦN RE-VERIFY.** `config/access_policies.json` có DEPARTMENT_USER với `["COMPANY_WIDE","DEPARTMENT"]`; `src/security/models.py:6-15` UserRole enum có 8 role gồm DEPARTMENT_USER; `backend/app/api/v1/endpoints/admin.py:20-30` ROLE_CAPABILITIES có đủ 10 role. Khả năng cao blocker thực tế chỉ là: EMPLOYEE hiện bị giới hạn `[COMPANY_WIDE]` (policy `ebb2744`) và không ai gán role DEPARTMENT_USER cho user thật. Phase 6 phải xác minh runtime trước khi kết luận.
3. **README/ARCHITECTURE quảng cáo "Hybrid Search Dense + BM25" như năng lực cốt lõi — nhưng `use_hybrid: bool = False` mặc định** (`src/config.py:349`, comment "Tắt mặc định để A/B"). Production path hiện tại = dense + rerank only. Cập nhật tài liệu hoặc bật kèm eval — không để docs nói hơn hệ thống.
4. **README mô tả "12 node" với grade/generate tách file — thực tế `grade_node` nằm trong `retrieval.py:367-389`, hallucination/confidence nằm trong `escalation.py`.** Nhỏ, chỉnh docs.
5. **Local workspace tụt sau origin/develop 7 commit** (knowledge layer Supabase + QC fix). Mọi con số baseline phải capture SAU khi pull.
6. Trạng thái release trong README (19/08) đã cũ so với báo cáo reconciliation 22/08.

---

## 2. Target State — "Pilot Ready" nghĩa là gì

Một pilot nội bộ ~10–20 user thật (nhân viên + 1–2 HR admin) chạy 2 tuần trên corpus hiện tại, với điều kiện:

- **Employee journey đóng kín**: login → hỏi → answer ≥1 citation ĐÚNG nguồn → mở citation thấy excerpt + version/hiệu lực → câu không có trong kho → REFUSED ổn định (cùng câu hỏi, cùng câu trả lời quyết định trong ≥95% lần chạy) → tạo ticket thủ công hoạt động.
- **Admin journey đóng kín**: login → upload file qua UI → thấy job tiến độ (stage + % + chunk_count) → INDEXED → hỏi được ngay trên tài liệu vừa upload → archive → không còn citation.
- **Trust**: không có case answer-nói-doc-A-nhưng-citation-trỏ-doc-B mà vẫn pass grounding.
- **Safety không regression**: toàn bộ test ACL/tenant/injection/PII pass; adversarial suite pass; out-of-corpus vẫn 10/10 abstain.
- **Debug được**: mỗi request trace được bằng request_id xuyên backend→agent; refusal rate, latency, rerank-degraded count đọc được từ 1 màn hình monitoring.
- **Secret sạch**: 2 credential đã lộ được rotate; không còn default secret yếu; CI có secret-scan.
- **Known limitations được ghi rõ** (không streaming, single-worker no-cron, corpus mô phỏng, ...).

---

## 3. Priority Matrix

| ID | Issue | Priority | Impact | Effort | Dependency | Status |
|---|---|---|---|---|---|---|
| B-1 | Nondeterminism (rerank fail-open + LLM borderline) | **P0** | Cao — phá trust | 2–3d | Pull remote trước | Remote đã làm 1 phần (temp=0, min_score) — cần verify + đóng nốt fail-open |
| B-2 | Citation attribution (grounding theo cited chunks) | **P0** | Cao — sai nguồn | 1.5–2d | Sau B-1 (cần deterministic để test) | Chưa làm |
| B-3 | Citation metadata (version/effective_date/code) | **P0** | Cao — đối soát pháp lý | 1–1.5d | Song song B-2 | Remote mới sync titles (BUG-01), chưa đụng read-path fields |
| B-4 | Unlock admin UI (upload/reindex/eval/monitoring) | **P1** | Cao — persona admin chết | 2–3d | Backend đã sẵn; chỉ frontend + 1 API monitoring | Chưa làm |
| B-5 | Over-refusal | **P1** | Trung bình — availability | 1–2d | Sau B-1 | Remote hạ ngưỡng + query expansion — cần verify |
| B-6 | Secrets/CI (rotate, JWT default, gitleaks) | **P1** | Cao nếu bỏ qua | 0.5–1d | Độc lập | Chưa làm |
| OBS | Observability tối thiểu | **P1** | Trung bình | 1.5–2d | Sau B-4 (cần monitoring API) | Có [audit] JSON + audit_logs, chưa có view |
| DPT | DEPARTMENT_USER decision + implement | **P1** | Trung bình (9 SOP đang khoá) | 1–2d | Sau B-1 (retrieval ổn định) | Cần verify discrepancy 1.4-2 |
| LAT | Latency/streaming | **P2** | Trung bình | 2–4d | Sau tất cả | p50 15s chấp nhận cho pilot |

---

## 4. Phase-by-Phase Plan

### Phase 0 — Baseline & Safety (0.5 ngày)

**Goal:** Workspace đồng bộ remote, baseline số liệu đóng băng, không sửa logic.

**Root cause:** N/A (chuẩn bị).

**Files/modules:** git, `Makefile`, `eval/`.

**Implementation:**
1. `git pull --ff-only` (local clean, chỉ 1 file untracked `docs/UX_PERSONA_QC_REPORT_20260822.md` — không cản trở). Verify commit `41263e9` có mặt: `git log --oneline -1 41263e9`.
2. Chạy: `make lint`, `make test`, backend `pytest tests/` (backend/), frontend `pnpm build`.
3. Khảo sát nhanh diff knowledge layer (9656bdb, 94e9a48) — không merge thêm thay đổi; chỉ xác nhận không đụng đường read-path đang sửa ở Phase 1–2.
4. Capture baseline vào `eval/results/baseline_pilot_20260823/`:
   - 10 câu lặp 3 lần (gồm "So sánh chính sách làm việc từ xa và nghỉ phép?", "Bảo hiểm?", 2 câu KPI/tuyển dụng): ghi state, citation doc_ids, rerank scores (có trong `[audit]` JSON line, `src/agents/service.py:163`) → refusal-flip count.
   - Retrieval dev split hiện có (`make eval-retrieval`) + router eval.
   - p50/p95 latency từ `stage_timings_ms` trong audit line.

**Dependencies:** none.
**Acceptance:** File baseline JSON commit; mọi số sau này so với nó.
**Tests:** N/A (chỉ đo).
**Regression risks:** none (không đổi code).
**Estimated effort:** 0.5 ngày.

### Phase 1 — Determinism (2–3 ngày)

**Goal:** Cùng câu hỏi → cùng quyết định (COMPLETED/REFUSED/FAILED-RETRYABLE), trừ khi hệ thống thật sự lỗi — khi đó phải nói rõ "lỗi hệ thống", không nói "không đủ bằng chứng".

**Root cause (đã xác minh code):**
1. `src/agents/nodes/retrieval.py:354-356` — rerank exception → fail-open: giữ thứ tự dense, `score=None`. Hệ quả dây chuyền:
   - `retrieval.py:383-387` grade: không có score → lọc bằng `distance <= retrieval_max_distance (0.18)` — câu hỏi so sánh/mở rộng thường có distance > 0.18 → danh sách rỗng.
   - `escalation.py:222-251` confidence: rơi công thức `(0.22 − d)/(0.22 − 0.10)` → thường < `low_confidence_threshold (0.2)` → `escalate` → backend map `REFUSED/INSUFFICIENT_EVIDENCE`.
   - Rerank chỉ retry 2 lần, timeout 60s (`src/services/fpt_client.py` defaults) — gateway chập chờn đủ để flip.
2. Nhiệt độ: local còn `generation.py:400 temperature=0.2`, `router.py:329,334 direct 0.5`, `router.py:347 clarify 0.4`, default `acall_llm = 0.5` (`src/agents/llm.py:20`). Remote `41263e9` đã sửa 4 call site này về 0.0 — còn default của hàm là 0.5 (bẫy cho call site mới/quên).
3. Marker `[KHÔNG_ĐỦ_THÔNG_TIN]` do LLM sinh (`generation.py:13,405`) — borderline query có thể flip ngay cả t=0 (nondeterminism phía provider, thinking mode). Tương tự `hallucination_passed` (LLM #2, `generation.py:494`).
4. `_merge_query_results` (`retrieval.py:121`) sort chỉ theo distance — equal-distance dựa insertion order; HNSW approximate search có thể dao động nhỏ ở vùng cutoff. Thiếu tie-break bằng chunk_id.

**Files/modules:** `src/agents/nodes/retrieval.py`, `src/agents/nodes/escalation.py`, `src/agents/llm.py`, `src/services/fpt_client.py`, `src/agents/service.py`, `tests/`.

**Implementation:**
1. **Rerank fail-open → fail-closed theo hướng "retryable failure"**: khi rerank lỗi sau retries, KHÔNG trả REFUSED (đó là phát biểu nghiệp vụ sai); trả về failure retryable tương tự AGENT_TIMEOUT hiện có (backend adapter đã có khái niệm `retryable`, xem `agent_answer_adapter.py` nhánh FAILED). Giữ nguyên hành vi hiện tại CHỈ khi cấu hình chủ động `rerank_fail_open=True` (env, mặc định False cho pilot). Gắn cờ `rerank_degraded` vào audit line + warnings của response.
2. **Đóng băng nhiệt độ**: đổi default `acall_llm` (`src/agents/llm.py:20`) 0.5 → 0.0; grep toàn bộ call site xác nhận không còn >0.0 (sau pull, remote đã sửa generation/direct/clarify).
3. **Tie-break deterministic**: `retrieval.py:121` đổi key sort thành `(distance, chunk_id)`; tương tự cho merge BM25/RRF nếu bật hybrid.
4. **Chống flip borderline của marker**: tăng `max_hallucination_retries`/thêm 1 lần "self-consistency" cho câu đi đến quyết định: nếu run 1 ra `[KHÔNG_ĐỦ_THÔNG_TIN]` NHƯNG confidence ≥ ngưỡng cao (ví dụ max rerank score ≥ 0.5) → retry generate 1 lần với prompt nhắc "chỉ trả marker khi thực sự không có thông tin"; 2/2 mới REFUSED. (Nguyên tắc: chi phí thêm 1 LLM call chỉ发生在 biên, không tăng latency trung bình.)
5. **Cache rerank** (optional): key = hash(query + chunk_ids) TTL ngắn — giảm cả determinism lẫn latency.

**Dependencies:** Phase 0.
**Acceptance criteria:**
- Bộ 10 câu × 5 lần chạy (live): 0 lần flip COMPLETED↔REFUSED do rerank degraded (rerank down → FAILED-retryable hiện rõ, không giả REFUSED).
- Decision + citation doc-set ổn định ≥ 95% (chừa 5% cho provider-side flips đã được mục 4 hấp thụ).
- Không tăng hallucination: adversarial + out-of-corpus suite pass như baseline.

**Tests:**
- Unit (mock LLM/rerank): `tests/test_agents/test_determinism.py` (mới) — (a) monkeypatch `rerank` raise → assert kết quả là retryable-failure, không phải REFUSED; (b) sort tie-break bằng chunk_id; (c) self-consistency path: run1 marker + score cao + run2 marker → REFUSED; run2 không marker → COMPLETED.
- Live E2E (E2E_LIVE=1): `tests/e2e/test_determinism_live.py` (mới) — 3 câu × 5 lần, assert stable state + citation set.

**Regression risks:** Đổi rerank fail-open → fail-closed làm tăng tỷ lệ FAILED-retryable khi gateway yếu — chấp nhận được (trung thực hơn REFUSED); đảm bảo backend FE hiển thị nút "Thử lại" (đã có, `ChatView.tsx` FAILED retryable branch).
**Estimated effort:** 2–3 ngày.

### Phase 2 — Citation Correctness (1.5–2 ngày + 1–1.5 ngày metadata)

**Goal:** (a) Không tồn tại case answer-nói-doc-A-citation-trỏ-doc-B mà pass grounding; (b) citation hiển thị đủ version/effective_date/document_code khi corpus có.

**Root cause (đã xác minh code):**
- Prose tự do: prompt `_GENERATE_SYSTEM` (`generation.py:41`) cho phép nêu "tên chính sách" trong văn; citation object bind deterministic từ chunk (`generation.py:419-440`); liên kết duy nhất là marker `[Nguồn N]` (`generation.py:178-213`). LLM đánh số lệch → prose/citation lệch nhau.
- Grounding check dùng pool toàn bộ retrieved chunks (`generation.py:466-473` tự chú thích) → mis-numbering pass.
- Read-path drop metadata: `_to_chunk` (`retrieval.py:181-209`) bỏ version/effective_date/document_code; `Citation` model (`src/models/schemas.py:162-198`) thiếu fields; adapter hardcode None (`agent_answer_adapter.py:84-85`); `citation_service.py:66-67` đọc → None.
- Title slug: `chunk_builder.py:19` fallback stem; accounting ingest không truyền title; synthetic chunk `retrieval_ext.py:246-272` có title bịa ngoài Chroma.
- BUG-01: `scripts/rag_pipeline/import_documents_to_supabase.py:30-43` upsert không có title → DB default 'Tài liệu không tên' (`backend/app/domain/models/documents.py:27`, migration 0001:45). (Remote đã thêm `scripts/sync_document_titles.py` chữa 1 lần — cần chữa tại nguồn.)

**Files/modules:** `src/agents/nodes/generation.py`, `src/agents/nodes/retrieval.py` (_to_chunk), `src/models/schemas.py`, `src/agents/state.py`, `backend/app/services/agent_answer_adapter.py`, `backend/app/services/citation_service.py`, `frontend/components/ChatView.tsx`, `scripts/rag_pipeline/import_documents_to_supabase.py`, `src/domains/accounting/retrieval_ext.py`.

**Implementation:**
1. **Canonical Citation object** — thêm fields vào `Citation` (schemas.py + state.py): `document_code`, `version`, `effective_date` (đã có `page`, `title`, `source_file`, `chunk_id`, tenant qua metadata). `_to_chunk` truyền qua từ Chroma metadata (fields đã tồn tại ở ingestion — `chunk_builder.py:89-92,181`). Adapter copy thay vì hardcode None. Frontend panel (`ChatView.tsx:527`) render `document_code · v{version} · hiệu lực {effective_date}` khi có.
2. **Grounding theo cited chunks** — sửa hallucination/grounding check: pool = các chunk thực sự được cite (sau `_keep_used_citations`) thay vì toàn bộ retrieved. Mis-numbering → grounding fail → dùng sẵn retry loop hallucination (`hallucination_retry_count`) → nếu vẫn fail → REFUSED/escalate thay vì trả answer gán nhầm. Thêm prompt 1 dòng: "Tên tài liệu trong văn bản PHẢI là tên hiển thị của [Nguồn N] tương ứng, không viết tên tài liệu khác."
3. **Validator deterministic sau generate**: với mỗi citation giữ lại, assert `marker [Nguồn N]` xuất hiện (đã có) VÀ excerpt thật sự nằm trong context của chunk N (string-level sanity). Rẻ, không LLM.
4. **Title tại nguồn**: `import_documents_to_supabase.py` thêm title vào upsert payload (lấy từ registry/Chroma như sync script); giữ `sync_document_titles.py` làm công cụ chữa dữ liệu 1 lần; runtime upload đã set title (`document_service.py:97`) — không cần đổi.
5. **Accounting synthetic chunk** (`retrieval_ext.py:246-272`): gắn `source_type="synthetic_guard"` + không cho vào citation panel display name bịa; hoặc tách riêng không cite. (SHOULD FIX — không chặn pilot nếu giờ đã có nhãn mô phỏng.)

**Dependencies:** Phase 1 (cần decision ổn định thì citation test mới meaningful).
**Acceptance criteria:**
- Unit test dựng lại chính kịch bản BUG-05 (answer nhắc "Quy chế Công tác phí" + marker trỏ chunk "quy-che-chi-tieu-noi-bo") → hệ thống hoặc tự sửa numbering ở retry, hoặc REFUSED — KHÔNG trả answer lệch.
- Mọi citation COMPLETED có document_code/version khi corpus có front-matter (verify trên 07_nghi-phep, 12_cong-tac-phi).
- Tenant isolation không đổi: citation chỉ chứa chunk đã qua ACL filter (test E2/E4 lại).
- `documents.title` bảng mới nhập không còn default 'Tài liệu không tên'.

**Tests:**
- `tests/test_agents/test_generation.py`: thêm `test_grounding_uses_cited_chunks_not_pool` (mis-numbering → fail grounding), `test_citation_carries_version_and_code`.
- `backend/tests/test_citations.py`: thêm assert version/effective_date truyền qua adapter + citation_service.
- E2E live: hỏi "Quy định về công tác phí?" → verify citation fields JSON.

**Regression risks:** Grounding chặt hơn → tăng REFUSED rate ở biên — đo lại bằng baseline 10 câu + dev split; nếu tăng >5 điểm phần trăm, xem lại prompt marker thay vì nới grounding.
**Estimated effort:** 2.5–3.5 ngày tổng.

### Phase 3 — Admin Knowledge Lifecycle (2–3 ngày)

**Goal:** Admin upload/index/monitor qua UI thật; E2E UI-level chạy được Journey B.

**Root cause:** Backend + worker đầy đủ (xem 1.4-1); blocker thuần frontend: static panel stale, không có form upload, không poll job, không có monitoring API.

**Files/modules:** `frontend/components/KnowledgeAdmin.tsx`, `frontend/lib/api.ts:336-361`, `backend/app/api/v1/endpoints/` (thêm monitoring), `backend/app/services/document_service.py` (không đổi logic chính), `src/workers/jobs.py` (không đổi).

**Implementation:**
1. **Upload UI**: thay static panel (`KnowledgeAdmin.tsx:57`) bằng form gọi `api.uploadDocument` (đã có): field file + scope/department/version/effective_date (optional); map error codes → message tiếng Việt: 415 UNSUPPORTED_FILE_TYPE, 413 FILE_TOO_LARGE, 422 FILE_NOT_MACHINE_READABLE, 409 DOCUMENT_ALREADY_EXISTS, 422 INVALID_ACCESS_SCOPE (codes có sẵn `document_service.py:75-144`).
2. **Job polling bắt buộc**: sau 201, poll `api.getIngestionJob(jobId)` theo `poll_after_ms` (backend ~1000ms) — LƯU Ý: DB state chỉ tiến triển KHI poll (mirror-on-poll, `document_service.py:479-497`). Hiện stage + progress_percent + chunk_count; FAILED → hiện error + gợi ý retry (tạo job mới upload lại). Kiểm tra state chứ không assume upload OK == indexed (agent down vẫn 201 + job FAILED).
3. **Wire Index & RAG + Evaluation**: `OperationsView` gọi `api.startIndexRebuild/getIndexRebuild/startEvaluation/getEvaluation` (đã có đủ trong api.ts). Giữ quy tắc single-active-job của backend (409 hiện có).
4. **Monitoring API (mới, nhỏ)**: `GET /admin/chat-requests/summary?window=24h` (HR_ADMIN+, tenant-scoped) aggregate từ bảng `chat_requests` (đã có question, state, latency_ms, citations, warnings, failure, retry_count — migration 0001:100-120): tổng request theo state, refusal rate, p50/p95 latency, top failed reasons, rerank_degraded count (field warnings sẽ có sau Phase 1). Không xây Prometheus/Grafana.
5. **requires_reindex flow**: PATCH metadata trả `requires_reindex: true` — thêm nút "Re-index ngay" dẫn sang job rebuild (đủ API sẵn).
6. **Archive propagation (P6)**: giữ soft-archive + query-time filter (an toàn); thêm 1 job worker nhỏ `archive-sync` xóa vector theo `(tenant, source_file)` khi archive — reuse `delete_by_source_stem`. Đưa về SHOULD FIX nếu thiếu thời gian.

**Dependencies:** Phase 0 (pull); không phụ thuộc Phase 1–2 (song song được nếu 2 người).
**Acceptance criteria:** Playwright/manual: admin upload file .md mới → thấy INDEXED + chunk_count → user hỏi nội dung file → có citation → archive → citation mất. Re-index job từ UI chạy đến COMPLETED. Monitoring hiển thị số thật từ DB.
**Tests:** `backend/tests/test_monitoring_api.py` (mới): auth HR_ADMIN, tenant-scoped, số liệu khớp fixture. Frontend: giữ `pnpm build` pass; thêm e2e manual checklist vào `docs/E2E_TEST_MATRIX.md`.
**Regression risks:** Thêm endpoint monitoring phải giữ RBAC + tenant filter — viết test tương tự test_admin_access.py; KHÔNG expose nội dung chat cross-user (chỉ aggregate, không trả question text của user khác cho HR_ADMIN — quyết định sản phẩm: chỉ trả counts + failure codes).
**Estimated effort:** 2–3 ngày.

### Phase 4 — Monitoring / Observability (1.5–2 ngày)

**Goal:** Đủ debug production issue: 1 request trace end-to-end, số liệu tổng hợp 1 chỗ.

**Hiện có (đã xác minh):** `[AUDIT-RETRIEVAL]` (retrieval.py:281-285), `[audit]` JSON giàu metric (service.py:163: confidence, answerable, hallucination_passed, escalate, citation_count, guardrail flags, `stage_timings_ms`, network_calls), `[guardrail]` logs, bảng `audit_logs` (migration 0009, RLS, viết tại admin.py:61 + document_service.py:396), health endpoints 2 service, `src/observability/llm_trace.py` timer. Thiếu: correlation ID xuyên backend→agent, nơi tổng hợp, secret-scan CI.

**Implementation:**
1. Backend sinh `X-Request-ID` (hoặc nhận từ FE) → truyền sang agent trong call worker + log mọi audit line kèm req_id (agent đã log req_id riêng — chuẩn hóa cùng giá trị).
2. Structured log JSON ra file (`logs/agent-YYYYMMDD.jsonl`) song song stdout; log rotation đơn giản theo ngày.
3. Monitoring view (Phase 3 mục 4) + thêm: indexing success/failure (từ ingestion_jobs), citation mismatch count (sau Phase 2 validator — đếm grounding-retry events), auth/ACL failure count (đếm từ audit lines sentinel `__NO_ACCESS__`).
4. CI secret-scan: thêm bước gitleaks vào `ci.yml`; fix 5 test live-FPT giả-key + cutover_smoke để CI xanh (env-gated skip).
5. Health/readiness nâng cấp: `/health` thêm check Supabase + Chroma reachability (readiness tách khỏi liveness).

**Acceptance:** Từ 1 chat_request_id, grep req_id ra được full chain (backend log + agent [audit] + [AUDIT-RETRIEVAL]). Monitoring view hiển thị refusal rate + rerank_degraded + p50/p95 theo giờ.
**Tests:** unit cho request-id propagation; e2e assert log lines chứa req_id.
**Effort:** 1.5–2 ngày.

### Phase 5 — Over-refusal (1–2 ngày)

**Goal:** Câu hỏi có doc trong corpus (KPI, tuyển dụng, performance review) trả lời được; out-of-corpus vẫn abstain 100%.

**Root cause candidates (phân loại theo taxonomy, dùng audit line có rerank scores):**
1. Retrieval miss / rerank score thấp → đã được remote `41263e9` hạ `rerank_min_score` 0.05→0.01 + query expansion — CẦN VERIFY, chưa có số.
2. Grader threshold — như trên (grade_node chỉ lọc theo cùng ngưỡng).
3. Router classification sai — router accuracy 95.7% baseline, khả năng thấp.
4. Marker sinh bởi LLM quá thận trọng — Phase 1 mục 4 (self-consistency) trị được phần này.

**Implementation:**
1. Chạy bộ "refusal analysis set" (10–15 câu E1/P3 + QC cases) trên dev (KHÔNG held-out); classify từng câu theo taxonomy bằng audit line (retrieved doc_ids có đúng doc? max score bao nhiêu? marker có sinh không?).
2. Chỉ can thiệp sau khi biết class: retrieval miss → improve query expansion/keywords (mẫu đã có); marker over-cautious → self-consistency Phase 1; KHÔNG hạ thêm ngưỡng nếu class không phải threshold.
3. Chạy lại đầy đủ: in-corpus dev (availability tăng), out-of-corpus 10 câu (0 fabrication), adversarial (không regression).

**Acceptance:** Bộ analysis set pass ≥ 90%; out-of-corpus vẫn 10/10 abstain; adversarial unchanged.
**Effort:** 1–2 ngày (sau khi remote fix được verify).

### Phase 6 — DEPARTMENT_USER (1–2 ngày)

**Bước 0 — verify discrepancy 1.4-2:** tạo user thật role DEPARTMENT_USER (SUPER_ADMIN qua `PATCH /admin/users/{id}/access`) → hỏi SOP phòng mình → kết luận runtime hoạt động hay thiếu wiring.

**Decision table đề xuất (product decision, không phải kỹ thuật):**

| Role | COMPANY_WIDE | DEPARTMENT (phòng mình) | DEPARTMENT (phòng khác) | ROLE-scope | RESTRICTED |
|---|---|---|---|---|---|
| EMPLOYEE | ✅ | ❌ | ❌ | ❌ | ❌ |
| DEPARTMENT_USER | ✅ | ✅ | ❌ | ❌ | ❌ |
| HR_ADMIN/ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ |

Lưu ý: predicate runtime đã có sẵn nhánh DEPARTMENT khớp `department == user.department` (`authorization.py:31-51`) — policy file đã định nghĩa role; việc còn lại chủ yếu là (a) quyết định có gán DEPARTMENT_USER cho user thật không, (b) nếu quyết định "EMPLOYEE đọc được SOP phòng mình" thì đổi `access_policies.json` EMPLOYEE thêm DEPARTMENT — ĐÂY LÀ THAY ĐỔI CHÍNH SÁCH, phải qua review + eval E2/E4 mở rộng, không làm để kéo availability.

**Acceptance:** Test E2 mở rộng: DEPARTMENT_USER đọc SOP phòng mình, KHÔNG đọc SOP phòng khác (predicate đã enforce — test khóa lại); audit log ghi khi đổi role.
**Effort:** 1–2 ngày.

### Phase 7 — Streaming & Latency (2–4 ngày, SAU 1–6)

**Profile trước (data có sẵn):** `stage_timings_ms` trong `[audit]` cho thấy phân bổ — kỳ vọng dominated bởi 3–4 LLM call tuần tự (condense→router→generate→hallucination) + rerank. Chỉ optimize sau khi có số.

**Ứng viên (đã khảo sát):** skip condense khi không có history (đã có); cache embedding query (đã có); cache rerank (Phase 1 mục 5); gộp hallucination_check vào generation prompt hợp đồng (đổi contract — cân nhắc); SSE streaming từ agent → backend → FE (FE hiện poll `GET /chat/requests/{id}` — thêm SSE endpoint song song, giữ poll làm fallback); nâng `AI_AGENT_TIMEOUT_SECONDS` > p95 thực đo + 1 retry nội bộ cho TIMEOUT retryable (B4/B5 transient).

**Không sacrifice:** security, citation binding, deterministic decisions.
**Effort:** 2–4 ngày.

---

## 5. Exact Task Backlog

**TASK-001 — Sync workspace + verify determinism commit**
- Priority: P0 | Depends: — 
- Files: git
- Changes: `git pull --ff-only`; confirm `41263e9` (temperature 0.0×4 call site, `rerank_min_score` 0.01, `_KPI_QUERY_PATTERN`/`_RECRUITMENT_QUERY_PATTERN`, `sync_document_titles.py`, `chunk_builder.resolve_title` slug cleanup).
- Tests: `make lint && make test && backend pytest && pnpm build`.
- AC: workspace = origin/develop; toàn bộ suite现状 pass (ghi lại các fail pre-existing).
- DoD: baseline suite chạy xong, kết quả lưu `docs/` hoặc issue.

**TASK-002 — Capture baseline metrics**
- P0 | Depends: TASK-001
- Changes: script nhỏ `scripts/eval/capture_pilot_baseline.py` chạy 10 câu ×3, thu state/citation/scores từ log `[audit]`; lưu `eval/results/baseline_pilot_20260823/`.
- AC: file JSON + markdown summary commit. Không đổi code logic.
- DoD: mọi PR sau này đối chiếu được với baseline này.

**TASK-003 — Rerank fail-closed (retryable failure thay vì giả REFUSED)**
- P0 | Depends: TASK-002
- Files: `src/agents/nodes/retrieval.py:331-364`, `src/agents/service.py`, `backend/app/services/agent_answer_adapter.py`
- Changes: rerank exception sau retries → kết thúc request là failure retryable (message "Hệ thống tạm quá tải, vui lòng thử lại"), KHÔNG chạy tiếp nhánh distance-fallback phát sinh REFUSED; thêm setting `rerank_fail_open` (default False); audit line thêm `rerank_degraded`.
- Tests: unit mock `rerank` raise → assert retryable failure; e2e assert FE hiện nút Thử lại.
- AC: rerank down không bao giờ sinh REFUSED/INSUFFICIENT_EVIDENCE.
- DoD: regression test + baseline 10 câu không còn flip do degraded path.

**TASK-004 — Temperature sweep + default 0.0**
- P0 | Depends: TASK-001
- Files: `src/agents/llm.py:20` (default 0.5→0.0), grep call sites.
- AC: không còn call site nào >0.0 trừ khi comment lý do rõ ràng.
- DoD: `grep -rn "temperature" src/agents` sạch.

**TASK-005 — Deterministic tie-breaking**
- P0 | Depends: TASK-001
- Files: `src/agents/nodes/retrieval.py:121` (sort key `(distance, chunk_id)`), `_amerge_bm25`/RRF nếu bật hybrid.
- Tests: unit construct equal-distance results → assert order theo chunk_id.
- DoD: test pass; không đổi metric retrieval (chạy dev split so baseline).

**TASK-006 — Self-consistency cho marker borderline**
- P0 | Depends: TASK-003
- Files: `src/agents/nodes/generation.py`, `src/agents/nodes/escalation.py`
- Changes: khi marker xuất hiện NHƯNG max rerank score ≥ 0.5 → retry generate 1 lần; 2/2 marker mới chốt REFUSED.
- Tests: unit 2 kịch bản (flip được hấp thụ / thật sự không证据 → vẫn REFUSED).
- AC: "So sánh WFH vs nghỉ phép?" ×5 chạy stable.
- DoD: e2e determinism suite pass ≥95%.

**TASK-007 — Canonical Citation fields qua read-path**
- P0 | Depends: TASK-001
- Files: `src/agents/nodes/retrieval.py:181-209` (_to_chunk), `src/models/schemas.py:162-198`, `src/agents/state.py`, `backend/app/services/agent_answer_adapter.py:84-85`, `frontend/components/ChatView.tsx:527`
- Changes: thêm `document_code`, `version`, `effective_date`; adapter copy từ chunk; FE render.
- Tests: unit adapter; e2e assert JSON có fields với doc 07/12 (front-matter có sẵn).
- DoD: panel không còn "Phiên bản — / Hiệu lực —" với docs có front-matter.

**TASK-008 — Grounding theo cited chunks + numbering validator (BUG-05)**
- P0 | Depends: TASK-006
- Files: `src/agents/nodes/generation.py:419-473`
- Changes: grounding pool = cited chunks; prompt thêm ràng buộc tên tài liệu; deterministic check marker↔chunk.
- Tests: `test_grounding_uses_cited_chunks_not_pool` dựng lại kịch bản BUG-05.
- AC: mis-numbering → retry → hoặc sửa hoặc REFUSED, không trả answer lệch.
- DoD: regression test pass; baseline citation correctness không giảm.

**TASK-009 — documents.title tại nguồn**
- P1 | Depends: TASK-001
- Files: `scripts/rag_pipeline/import_documents_to_supabase.py:30-43`
- Changes: thêm title vào upsert payload (từ registry/Chroma); chạy `sync_document_titles.py` 1 lần chữa dữ liệu cũ.
- DoD: bảng documents không còn 'Tài liệu không tên' với corpus hiện tại; test chặn tái diễn (payload có title).

**TASK-010 — Unlock Upload UI + job polling**
- P1 | Depends: TASK-001
- Files: `frontend/components/KnowledgeAdmin.tsx:57`, `frontend/lib/api.ts:336-351`
- Changes: form upload + error mapping (415/413/422/409) + poll job theo `poll_after_ms` + stage/progress/chunk_count + FAILED surface.
- AC: manual e2e upload→INDEXED→hỏi→citation.
- DoD: checklist Journey B pass qua UI.

**TASK-011 — Wire Index/Eval operations UI**
- P1 | Depends: TASK-010
- Files: `KnowledgeAdmin.tsx:68-73` (OperationsView), `api.ts:346-361` (startIndexRebuild/getIndexRebuild/startEvaluation/getEvaluation)
- DoD: tạo rebuild job + eval run từ UI, xem status đến terminal state.

**TASK-012 — Monitoring API + view**
- P1 | Depends: TASK-010
- Files: `backend/app/api/v1/endpoints/admin.py` (+router), service mới, `HrKnowledgeApp.tsx:79` DeferredView
- Changes: `GET /admin/chat-requests/summary` aggregate chat_requests (counts theo state, refusal rate, p50/p95, failure codes, rerank_degraded); RBAC HR_ADMIN+; tenant-scoped; KHÔNG trả question text cross-user.
- Tests: `backend/tests/test_monitoring_api.py` (auth + tenant + số liệu).
- DoD: "Giám sát truy vấn" hiển thị số thật.

**TASK-013 — Request-ID correlation + JSON file logs**
- P1 | Depends: TASK-003
- Files: backend middleware + `worker_job_client.py` header; `src/agents/service.py:163`
- DoD: grep req_id ra full chain; file jsonl hàng ngày.

**TASK-014 — Secrets hardening**
- P1 | Depends: —
- Files: `backend/app/core/config.py:45` (xóa default "12345678900aaa" → raise nếu thiếu ở prod), `.github/workflows/ci.yml` (gitleaks), docs runbook rotation.
- Changes: rotate 2 credential đã lộ (HÀNH ĐỘNG MANUAL chủ repo —-track trong issue).
- DoD: CI có secret-scan; app không khởi động prod với JWT default; credentials rotated.

**TASK-015 — Over-refusal verification + remediation**
- P1 | Depends: TASK-003, TASK-006
- Files: phân tích trước (audit lines), sau đó `retrieval.py` query expansion nếu cần.
- AC: analysis set ≥90% pass; out-of-corpus 10/10 abstain; adversarial pass.
- DoD: báo cáo phân loại root-cause + fix cụ thể theo class.

**TASK-016 — DEPARTMENT_USER verify + policy decision**
- P1 | Depends: TASK-015
- Files: `config/access_policies.json`, test E2 mở rộng.
- DoD: decision table ký duyệt; runtime verified; test khóa hành vi.

**TASK-017 — Latency profile + quick wins**
- P2 | Depends: Phase 1–6 done
- Files: theo profile (cache rerank, timeout alignment `AI_AGENT_TIMEOUT_SECONDS`).
- DoD: p95 giảm có số so baseline; B4/B5 hết transient fail.

**TASK-018 — Streaming SSE (optional pilot)**
- P2 | Depends: TASK-017
- Files: agent API + backend + FE.
- DoD: token stream hiển thị; fallback poll giữ nguyên.

---

## 6. Dependency Graph

```
Phase 0: TASK-001 (pull) → TASK-002 (baseline)
   ↓
Phase 1 Determinism: TASK-003 (rerank fail-closed) ─┬→ TASK-006 (self-consistency)
   TASK-004 (temp), TASK-005 (tie-break) ────────────┘
   ↓
Phase 2 Citation: TASK-007 (fields) ∥ TASK-008 (grounding — needs TASK-006)
   TASK-009 (titles, song song từ Phase 0)
   ↓
Phase 3 Admin: TASK-010 (upload UI) → TASK-011 (ops UI) → TASK-012 (monitoring)
   ↓
Phase 4 Observability: TASK-013 (req-id) — sau TASK-003; TASK-014 (secrets) — độc lập, làm sớm nhất có thể
   ↓
Phase 5 Over-refusal: TASK-015 (cần determinism xong để đo đúng)
   ↓
Phase 6 DEPARTMENT_USER: TASK-016
   ↓
Phase 7 Latency: TASK-017 → TASK-018
```

Ghi chú: TASK-014 (secrets) và TASK-009 không chặn ai — chạy song song bất kỳ lúc nào. TASK-010–012 chỉ phụ thuộc pull, có thể chạy song song Phase 1–2 nếu có 2 người.

## 7. Test Matrix

| Test | Before (baseline cần capture TASK-002) | After | Expected |
|---|---|---|---|
| Determinism 10 câu ×5 | Có flip COMPLETED↔REFUSED (DATA-01: 2/10 câu flip khi QC) | Đo lại | 0 flip do rerank; ≥95% stable decision+citation set |
| Citation correctness | 1 case mis-attribution thực đo (BUG-05); version/effective 0% hiển thị | Đo lại | 0 mis-attribution pass grounding; fields hiển thị 100% với doc có front-matter |
| Hallucination / abstain | 10/10 out-of-corpus abstain | Giữ | 10/10, không regression |
| ACL / tenant | E2/E4/F1/F2 pass | Giữ | 100% pass |
| Upload E2E (UI) | Blocked (UI khóa) | Mới | Journey B pass qua UI |
| Re-index/eval (UI) | Locked | Mới | Job đến COMPLETED từ UI |
| Refusal (analysis set) | E1/P3 REFUSED dù có doc | Đo lại | ≥90% trả lời được |
| Latency p50/p95 | p50 ~15s / max ~48s (QC 22/08) | Sau Phase 7 | p95 giảm có số; không target cứng giai đoạn pilot |
| Security suite | Pass (remediation 22/08) | Giữ | 100% pass mỗi PR |

Số "Before" nghiêm cấm bịa thêm: mọi ô "?" phải lấy từ TASK-002 trước khi mở PR đổi hành vi.

## 8. Risk Register

| Risk | Severity | Probability | Mitigation | Owner |
|---|---|---|---|---|
| Rerank fail-closed làm tăng FAILED khi gateway yếu | Medium | Medium | Thông điệp rõ + nút retry; monitoring đếm rerank_degraded | AI Eng |
| Grounding chặt → tăng REFUSED | Medium | Medium | Đo baseline trước/sau; chỉ chấp nhận nếu swap mis-citation→retry/REFUSED | AI Eng |
| Over-refusal fix tăng hallucination | High | Medium | Adversarial + out-of-corpus chạy sau mỗi đổi ngưỡng | AI Eng |
| Pull 7 commit gây bất ổn (knowledge layer mới chưa test local) | Medium | Low | Fast-forward + full suite ở TASK-001 | AI Eng |
| Credential đã lộ chưa rotate | High | — | TASK-014, hành động manual ngay | Repo owner |
| Scope creep (knowledge layer/relation detection) | High | High | Mục 10 WHAT NOT TO BUILD | PM + AI Eng |
| Frontend upload poll spam backend | Low | Medium | Poll theo `poll_after_ms` + backoff tối đa 30s | FE |

## 9. Definition of Pilot Ready (checklist verificable)

1. ✅ TASK-001→009, 012→015 hoàn thành; các mục P2 (latency/streaming) KHÔNG bắt buộc.
2. Determinism: bộ 10 câu ×5 lần, 0 flip do hạ tầng; decision stable ≥95%.
3. Citation: không có case answer-vs-citation mismatch pass grounding (test khóa BUG-05); version/effective_date hiển thị với doc có metadata.
4. Admin: upload→INDEXED→searchable→archive mất citation, toàn bộ qua UI.
5. Monitoring: refusal rate, latency, rerank_degraded, indexing status đọc được từ UI admin.
6. Security regression = 0: E/F/H suite + tenant isolation + trigger tests pass trong CI.
7. Hallucination regression = 0: adversarial + out-of-corpus pass như baseline.
8. Secrets: 2 credential rotated; CI gitleaks xanh; không default JWT secret ở prod.
9. Known limitations documented trong README (mục mới): corpus mô phỏng, không streaming (nếu Phase 7 chưa xong), single-worker, use_hybrid=False, DEPARTMENT policy theo decision table.

## 10. What NOT to Build Yet (defer khỏi pilot)

- **Relation detection / SUPERSEDES / CONFLICTS_WITH** (vừa land ở remote `9656bdb` — giữ nguyên, không wire vào agent graph).
- **Generic structured knowledge extraction runtime + HITL UI mở rộng** (knowledge layer mới chỉ giữ ở mức đã có; không nối vào luồng chat pilot).
- **Multi-domain expansion** (Product/Accounting đã có collection — không thêm domain mới).
- **Celery/Redis/Kafka/cron**: kiến trúc worker-on-poll hiện tại đủ cho pilot 10–20 user; introduce queue = scope creep hạ tầng.
- **Prometheus/Grafana**: JSON endpoint + view là đủ.
- **Dark mode, notification toast, mobile drawer, browse/search tài liệu cho employee** (PRD-02 nice-to-have).
- **URL routing/deep-link** (UX-05) — defer.
- **Chroma→pgvector migration** — không đụng.

## 11. Recommended Execution Order (PR sequence)

| PR | Nội dung | Tasks | Gate merge |
|---|---|---|---|
| PR-00 | Sync + baseline (không đổi logic) | 001, 002 | baseline file committed |
| PR-01 | Determinism | 003, 004, 005, 006 | determinism suite ≥95%; adversarial pass |
| PR-02 | Citation | 007, 008, 009 | BUG-05 regression test pass; E2/E4 pass |
| PR-03 | Admin unlock + monitoring | 010, 011, 012 | Journey B UI pass; monitoring test pass |
| PR-04 | Observability + secrets | 013, 014 | req_id chain demo; CI gitleaks xanh |
| PR-05 | Over-refusal | 015 | analysis set ≥90%; out-of-corpus 10/10 |
| PR-06 | DEPARTMENT_USER | 016 | decision table + test |
| PR-07 | Latency/streaming (post-pilot-kickoff được) | 017, 018 | profile-before-optimize |

Khác biệt so với thứ tự gợi ý ban đầu: secrets (TASK-014) tách thành PR riêng và làm NGAY SỚM (song song PR-01) vì đã có credential lộ thật; title sync (TASK-009) gộp vào PR-02 vì cùng chạm chuỗi metadata.

## 12. Final Verdict

**Đang ở đâu:** Nền kỹ thuật (security, eval, worker ingestion) đã ở mức tốt bất thường cho dự án môn học; khoảng cách tới pilot KHÔNG phải kiến trúc mà là 4 lỗ hổng chất lượng đúng vào lời hứa cốt lõi: determinism, citation trust, admin portal đóng, observability mù.

**Còn bao nhiêu blocker:** 6 blocker (B-1→B-6), trong đó **critical cho lời hứa sản phẩm: B-1 (nondeterminism) và B-2 (citation attribution)** — đã có root-cause chính xác đến dòng code và giải pháp không cần rewrite. **B-6 (credential) là critical về an toàn nhưng rẻ nhất** (0.5–1 ngày, chủ yếu manual rotation).

**Nếu 1 AI Engineer làm:** tuần 1 = PR-00 + PR-01 + PR-02 (determinism + citation — hai thứ bảo vệ trust); tuần 2 = PR-03 + PR-04 (mở admin portal + thấy được hệ thống); tuần 3 = PR-05 + PR-06 (availability + policy) rồi chốt pilot checklist mục 9. Tổng ~3 tuần tập trung.

**Tuyệt đối không làm lúc này:** mọi thứ trong mục 10 — đặc biệt là wire knowledge layer/relation detection mới từ remote vào agent graph, và introduce hạ tầng queue. Success criterion của pilot là "một nhân viên tin được câu trả lời và một admin vận hành được kho tài liệu", không phải số feature.
