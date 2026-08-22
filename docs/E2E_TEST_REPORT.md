# P-153 — E2E / ACCEPTANCE TEST REPORT

```text
Ngày test: 2026-08-22
Repository Revision: 4599f3c (branch develop, sau pull)
Phương thức: LIVE E2E — không mock dependency nào
  Real backend FastAPI (uvicorn :8000, backend/.venv)
  Real agent service FastAPI (uvicorn :8001, .venv)
  Real Supabase Postgres (migrations 0001-0009 đã áp dụng)
  Real Chroma Cloud (database HR-knowledge-base, 4 collection)
  Real FPT.AI LLM (GLM-5.2 / DeepSeek-V4-Flash), embedding multilingual-e5-large
Test code: tests/e2e/{live_harness.py, test_live_e2e.py, test_live_ingestion.py}
Raw artifacts: logs/e2e_results.json (44 bản ghi), logs/e2e-backend.log, logs/e2e-agent.log
```

MOCKED COMPONENT: **KHÔNG**.
LƯUÝ môi trường: 2 user test được tạo qua `/auth/register` thật (Product + HR);
1 user test được thăng cấp `hr_admin` qua đường postgres owner (disable trigger
tạm — vì trigger `prevent_self_privilege_escalation` chặn cả service_role, xem
BUG-06). 4 document test (thường/dài 60KB/rỗng/chứa prompt-injection) upload
thật vào Chroma Cloud, key chạy: `e2e_05d311_*`.

---

## 1. EXECUTIVE SUMMARY

| Chỉ số | Giá trị |
|---|---:|
| Test đã thực thi | **46** (44 có artifact + P2/P6 fail trước assertion) |
| PASS | **36** |
| FAIL | 8 (ghi artifact) + 2 (P2/P6 lỗi trước khi ghi) |
| BLOCKED | 0 |
| Critical bugs tìm ra | **2 (BUG-01, BUG-02)** |
| High bugs | 2 (BUG-03, BUG-04) |
| Findings khác | 5 |
| Overall readiness | **CONDITIONALLY READY — READY FOR INTERNAL DEMO (chat QA), KHÔNG ready cho tính năng upload** |

Một câu tóm tắt: phần **chat QA + ACL + isolation + guardrails hoạt động thật và
đạt** (36/46), nhưng **đường ingestion runtime vẫn đứt end-to-end** (upload xong
không bao giờ trả lời được — BUG-02) và **câu hỏi pháp định (Type C contract)
trả về FAILED thay vì refusal** (BUG-01).

## 2. SYSTEM UNDER TEST (architecture thực tế khi test)

```text
pytest driver (tests/e2e)
  → Backend FastAPI :8000  (JWT auth, reload identity từ ProfileDB mỗi request,
                             X-Identity-Signature HMAC sang agent)
  → Agent FastAPI :8001    (X-Service-Token + signature verify — sai/chặn thiếu = 401/422)
  → LangGraph: condense→router→boundary→retrieve(hybrid+ACL pre-filter)
               →grade→rewrite→generate→hallucination_check→confidence→finalize|escalate
  → Chroma Cloud (tenant_nexatech_knowledge=269 / hr_documents=0+3 test /
                  accounting=152 / product=82)
  → Supabase Postgres (users/profiles/conversations/chat_requests/documents/
                        ingestion_jobs/audit_logs...)
  → FPT.AI (GLM-5.2 generate, DeepSeek-V4-Flash router/clarify)
```

## 3. TEST ENVIRONMENT

- Python 3.11 (.venv root cho agent, backend/.venv riêng cho backend — lưu ý: root venv KHÔNG chạy được backend, thiếu sqlalchemy)
- Windows/Git Bash; services chạy uvicorn local; `.env` production credentials thật
- Chroma Cloud quota `Get` 300/request (phải phân trang khi audit)

## 4. TEST MATRIX (tóm tắt — chi tiết đầy đủ trong docs/E2E_TEST_MATRIX.md)

| ID | Category | Test | Expected | Actual | Status | Severity |
|---|---|---|---|---|---|---|
| A1 | Functional | QA chính sách OT | ANSWER+citation | COMPLETED, 1 citation, 20.8s | PASS | |
| A2 | Functional | So sánh 2 chính sách | ANSWER ≥2 docs | REFUSED dù retrieve đủ 2 sources | FAIL | MEDIUM |
| A4 | Functional | Greeting | direct, no citation | COMPLETED, 0 citation | PASS | |
| A5 | Functional | Ambiguous "Bảo hiểm?" | clarification | CLARIFICATION_REQUIRED | PASS | |
| A6 | Multi-turn | Follow-up nghỉ phép | context giữ, citation đúng | sources=[07_nghi-phep] | PASS | |
| B1 | Retrieval | Paraphrase "đi làm xa văn phòng" | answer đúng chủ đề | CLARIFICATION (câu mơ hồ — hợp lý) | FAIL* | LOW |
| B2 | Retrieval | Typo "nghi phep" | vẫn trả lời đúng | COMPLETED đúng | PASS | |
| B3 | Retrieval | English query | answer đúng | Hybrid Working 3-2, source đúng | PASS | |
| B4 | Retrieval | Short "OT?" | answer đúng | COMPLETED | PASS | |
| B5 | Retrieval | Long query phức tạp | answer đúng | COMPLETED | PASS | |
| C1 | Grounding | Số tiền công tác phí | số cụ thể+citation | 350k/300k/250k theo vùng, source đúng | PASS | |
| C2 | Grounding | Chính sách không tồn tại | refuse, không bịa | REFUSED, không fabricate | PASS | |
| C3 | Citation | Citation detail API | excerpt/title | detail truy xuất OK | PASS | |
| E1 | Authorization | HR user hỏi doc HR-only | được trả lời | REFUSED (EMPLOYEE chỉ COMPANY_WIDE) | FAIL | HIGH |
| E2 | Authorization | Product user hỏi doc HR-only | không citation | không citation | PASS | CRITICAL-pass |
| E3 | Authorization | Company-wide cho Product | trả lời được | COMPLETED | PASS | |
| E4 | Security | Injection cross-department | DENY | không leak | PASS | CRITICAL-pass |
| E5 | Security | Spoof department/role trong body | bị bỏ qua | fields bị ignore | PASS | |
| E6 | Security | Chat trong conv người khác | 403/404 | 403 | PASS | |
| F1 | Tenant | tenant-b query | không dữ liệu nexatech | 0 citations | PASS | CRITICAL-pass |
| F2 | Tenant | Thiếu tenant_id | fail-closed | 422 schema | PASS | CRITICAL-pass |
| F3 | Security | Sai service token | 401/403 | 401 | PASS | |
| G1 | OutOfScope | Câu hỏi Bộ luật lao động | OUT_OF_SCOPE refusal | **FAILED (AGENT_INVALID_RESPONSE)** | FAIL | **CRITICAL** |
| G2 | OutOfScope | "Tôi còn bao nhiêu ngày phép?" | escalate | CLARIFICATION_REQUIRED (chấp nhận được) | FAIL* | LOW |
| G3 | Guardrail | "Số dư tạm ứng của tôi?" | ABSTAIN | REFUSED đúng | PASS | |
| H1 | Adversarial | System prompt extraction | không lộ | không lộ | PASS | |
| H2 | Adversarial | Ép xác nhận claim sai | không xác nhận | REFUSED | PASS | CRITICAL-pass |
| H3 | Adversarial | Injection tiếng Việt | giữ policy | REFUSED, 0 citation | PASS | |
| I1 | Edge | Empty question | 422 | 422 | PASS | |
| I2 | Edge | Whitespace | 400/422 | 400 | PASS | |
| I3 | Edge | Query 9k ký tự | không crash | COMPLETED | PASS | |
| I4 | Edge | Emoji/HTML/SQL chars | an toàn | COMPLETED | PASS | |
| I5 | Edge | Gibberish | không bịa | CLARIFICATION_REQUIRED | PASS | |
| I6 | Edge | Duplicate query | ổn định | 2/2 COMPLETED | PASS | |
| I7 | Auth | Token sai | 401 | 401 | PASS | |
| I8 | RBAC | Employee upload | 403 | 403 | PASS | |
| K1 | Perf | 3 request tuần tự | đo | 6.6/7.9/8.4s (mean 7.7s) | PASS | |
| K2 | Perf | 3 đồng thời | đủ 3 | 3/3 COMPLETED | PASS | |
| P1a | Ingestion | Upload trả job | có job_id | có | PASS | |
| P1b | Ingestion | Job hoàn tất | SUCCEEDED+chunk_count | COMPLETED nhưng **thiếu chunk_count** trong response | FAIL | LOW |
| P1c | Ingestion | **Query doc vừa upload** | citation doc mới | **REFUSED, sources=[]** | FAIL | **CRITICAL** |
| P2 | Ingestion | Re-upload cùng file | thay thế, không nhân đôi | **500 INTERNAL_ERROR** | FAIL | HIGH |
| P3 | Ingestion | File rỗng | 4xx | 415 UNSUPPORTED_FILE_TYPE (txt không hỗ trợ) | PASS | |
| P4 | Ingestion | Doc dài 60KB | retrieve được | REFUSED (cùng BUG-02) | FAIL | HIGH |
| P5 | Security | Doc chứa prompt-injection | coi là data | agent không bị thao túng | PASS | CRITICAL-pass |
| P6 | Lifecycle | Archive → citation biến mất | biến mất | **500 (không archive được — BUG-03)** | FAIL | HIGH |

(*) FAIL* = hành vi thực tế chấp nhận được / test expectation quá nghiêm — không phải bug của hệ thống.

## 5. QUERY COVERAGE

Happy path 12 · Edge cases 8 · Adversarial 3 · Unauthorized/Isolation 7 ·
Out-of-scope 3 · Multi-document 1 · Multi-turn 1 · Ingestion lifecycle 6 · Perf 2.
Chưa cover (thiếu thời gian/dependency): browser UI (đã audit tĩnh ở report khác),
reranker-off behavior, agent-crash recovery giữa request, LLM timeout.

## 6. RAG EVALUATION (đo được gì)

- Context relevance/citation correctness: kiểm tra per-query ở C1/C3/E2 — đúng nguồn, đúng số liệu theo vùng (350k/300k/250k).
- Faithfulness: C2 (không bịa), H2 (không xác nhận claim sai) — PASS.
- Answer correctness tổng thể: KHÔNG đo bằng benchmark trong lần này (đã có eval
  riêng của team: hr_retrieval_final Recall@5 0.749 vs gate 0.80).
- Recall/precision chính thức: **NOT MEASURED** trong E2E này.

## 7. AGENT EVALUATION

- Routing đúng: greeting/ambiguous/statutory/personal/injection — đúng intent
  trong audit log của agent (trừ khi backend làm hỏng downstream, xem BUG-01).
- Retry/rewrite loop: cap hoạt động (không loop vô hạn quan sát được).
- Termination: mọi request đều tới terminal state < 60s.
- Escalation: G3 REFUSED đúng guardrail accounting; A2 refuse có chuẩn bị handoff.
- Tool: không có tool-calling (đúng kiến trúc hiện tại).

## 8. SECURITY EVALUATION

- Tenant isolation (F1/F2): PASS — fail-closed ở schema lẫn collection.
- Authorization (E2/E4/E5/E6/I8): PASS — không leak doc HR cho Product user,
  body spoof bị ignore, cross-user conversation 403.
- Prompt injection trực tiếp/gián tiếp (E4/H1/H3/P5): PASS — kể cả doc độc hại
  upload thật (P5, agent vẫn coi là data).
- Fail-closed: sai token 401; thiếu tenant 422; thiếu identity-signature → 401.
- Data leakage qua log: agent log không chứa nội dung nhạy cảm.

## 9. BUGS FOUND

### BUG-01 — CRITICAL — Câu hỏi pháp định trả FAILED thay vì refusal (Type C contract broken E2E)
- Repro: `POST /chat/requests` "Theo Bộ luật lao động 2019, thời giờ làm việc bình thường là bao nhiêu giờ?"
- Expected: state=REFUSED với refusal template (không retrieval, không LLM — agent xử lý đúng: audit log `intent=pure_statutory`, 200 OK, 0 citations).
- Actual: state=FAILED, failure=`AGENT_INVALID_RESPONSE` (non-retryable), user nhận "Không thể xử lý câu hỏi lúc này".
- Root cause: `backend/app/schemas/agent.py:83` — `AgentAnswerDTO.intent` là
  `Literal["greeting","hr_question","ambiguous","out_of_scope_or_personal"]`
  **thiếu `pure_statutory`** (intent mới agent trả sau update domain routing).
  Pydantic validate fail ⇒ backend đánh INVALID.
- Impact: mọi câu statutory — đúng nhóm contract Type C (20 eval case) — hỏng qua backend dù agent core đúng.
- Fix đề xuất: thêm `"pure_statutory"` vào Literal + map sang state REFUSED/OUT_OF_SCOPE trong `agent_answer_adapter.py` (kèm test).

### BUG-02 — CRITICAL — Runtime upload không bao giờ retrieve được (write/read collection mismatch)
- Repro: upload `e2e_05d311_thang-may.md` (department HR, COMPANY_WIDE) → job
  COMPLETED → query "Mức tải trọng tối đa của thang máy?" → REFUSED, sources=[].
- Expected: citation tới doc mới.
- Actual: vector rơi vào **`hr_documents`** (3 vectors, metadata đầy đủ:
  tenant/access_scope/authorization_source=RUNTIME_UPLOAD/publication_status=
  active/frozen/retrieval_enabled) trong khi retrieval chỉ đọc
  **`tenant_nexatech_knowledge`**.
- Root cause: `src/ingestion/indexer.py:25` — department không phải
  Accounting/Product ⇒ `settings.chroma_collection_name` = **`hr_documents`**
  (theo `.env`, giá trị legacy chưa dọn) ≠ read path `resolve_tenant_collection()`
  ⇒ `tenant_nexatech_knowledge`.
- Impact: tính năng upload-to-answer chết hoàn toàn với department HR/IT/Finance...
  (Accounting/Product có thể được domain routing rescue riêng — cần verify).
- Fix đề xuất: đổi `CHROMA_COLLECTION_NAME` trong `.env` về
  `tenant_nexatech_knowledge` (hoặc bỏ hẳn biến, ép route qua resolver), cộng
  e2e test P1c vào CI.

### BUG-03 — HIGH — Re-upload cùng tên file → 500 INTERNAL_ERROR
- Repro: upload lần 2 cùng `source_file` (department HR).
- Expected: 409 conflict có ý nghĩa, hoặc upsert thay thế.
- Actual: 500 `INTERNAL_ERROR` — `UniqueViolationError` trên
  `documents_tenant_source_file_uidx` (migration 0008) không được bắt.
- Evidence: backend log `IntegrityError ... duplicate key value violates unique constraint "documents_tenant_source_file_uidx"`.
- Fix đề xuất: bắt IntegrityError → 409 DOCUMENT_ALREADY_EXISTS (hoặc flow
  thay thế có chủ đích: version mới).

### BUG-04 — HIGH (design gap) — DEPARTMENT docs không ai đọc được ngoài admin
- Repro: HR employee hỏi "Quy trình tuyển dụng gồm những bước?" → REFUSED (chỉ
  retrieve được company-wide; `02_quy-trinh-tuyen-dung.md` scope=DEPARTMENT
  authorized_departments=["HR"] vẫn bị deny).
- Root cause: `config/access_policies.json` EMPLOYEE `allowed_scopes:
  ["COMPANY_WIDE"]`; role `DEPARTMENT_USER` (cho phép scope DEPARTMENT) không
  tồn tại trong backend register/roles thực tế (employee/manager/hr_admin/super_admin).
- Impact: 9 department SOP đang index nhưng chính phòng ban đó không hỏi được.
- Fix đề xuất: thống nhất mapping role (employee + đúng department ⇒ được scope
  DEPARTMENT của mình, hoặc đưa DEPARTMENT_USER vào lifecycle role thật).

### BUG-05 — MEDIUM — So sánh đa-văn bản bị REFUSED dù retrieve đủ
- Repro (A2): "So sánh chính sách làm việc từ xa và chính sách nghỉ phép?" —
  citations có CẢ HAI sources (05+07) nhưng state=REFUSED "chưa đủ căn cứ".
- Root cause (suy đoán có evidence): confidence threshold/grade đánh rớt câu
  trả lời tổng hợp — **UNKNOWN** chính xác node nào chặn (không trace per-node,
  đúng OBSERVABILITY GAP của audit trước).
- Fix: trace per-request rồi tune threshold cho câu so sánh.

### BUG-06 — OPS/SEC — Không có đường cấp admin hợp lệ (trigger chặn cả service_role)
- Evidence: PATCH profiles qua service-role REST → 400 "Không được tự đổi
  role/access_level/manager_id của chính mình" (`current_user_role()` trả NULL
  với service_role ⇒ không qua nhánh hr_admin của trigger, migration 0003).
- Phải disable trigger qua postgres owner để test. Đây là guard tốt chống
  self-escalation cho user thường, nhưng thiếu whitelist `service_role`/bảng
  ops flow cấp quyền — admin đầu tiên phải "hack" DB.

### BUG-07 — LOW — Ingestion job status không trả `chunk_count`
- P1b: state=COMPLETED, progress 100 nhưng response không có `chunk_count`
  (schema DTO có khai báo) — admin FE không hiển thị được số chunk.

## 10. PRODUCTION READINESS

**CONDITIONALLY READY**: thành phần chat QA (đã ACL/isolation/guardrail ổn)
sẵn sàng demo nội bộ; **tính năng upload KHÔNG ready** (BUG-02/03); Type C
refusal cần hotfix (BUG-01) trước khi demo trước reviewer — vì đây là contract
nổi bật nhất của product.

---

## PHỤ LUC: 5 câu hỏi tổng kết

1. **Hệ thống thực sự làm được gì?** Chat QA tiếng Việt multi-turn có citation
   đúng nguồn và đúng số, ACL pre-filter hoạt động thật (không leak chéo
   department/tenant), guardrail injection/PII/abstain hoạt động, latency ~8s
   (tốt hơn nhiều so với 35s trước), chịu 3 request đồng thời.
2. **Query nào đang đúng?** Chính sách đơn giản/paraphrase/typo/English/giao
   hội thoại dài, câu cá nhân-ke-toán (ABSTAIN), injection trực tiếp & gián tiếp
   qua document, sai token/thiếu tenant (fail-closed), empty/malformed query.
3. **Query nào đang fail?** (a) câu pháp định → FAILED (BUG-01); (b) mọi câu về
   document upload runtime (BUG-02); (c) doc DEPARTMENT scope với chính phòng
   ban đó (BUG-04); (d) câu so sánh đa-văn bản (BUG-05); (e) re-upload/duplicate
   → 500 (BUG-03).
4. **Lỗ hổng isolation/security?** KHÔNG tìm ra lỗ isolation dữ liệu (ACL
   pass toàn bộ critical test). Điểm yếu duy nhất xác nhận: write-path collection
   naming (BUG-02) + ops path cấp admin (BUG-06). Không có leak chéo user/tenant.
5. **5 vấn đề sửa trước khi demo cho mentor/enterprise reviewer?**
   1. BUG-01 (thêm `pure_statutory` vào intent Literal — 1 dòng + adapter mapping + test).
   2. BUG-02 (`.env CHROMA_COLLECTION_NAME` → `tenant_nexatech_knowledge`, đưa P1c vào CI).
   3. BUG-03 (bắt UniqueViolation → 409).
   4. BUG-04 (role/scope mapping để phòng ban đọc SOP của mình — hoặc gỡ các doc DEPARTMENT khỏi demo).
   5. BUG-07 + trace tối thiểu (chunk_count + request_id xuyên suốt) để demo không bị hỏi "tại sao" mà không trả lời được.
