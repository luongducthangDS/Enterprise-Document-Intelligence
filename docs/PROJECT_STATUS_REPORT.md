# P-153 — BÁO CÁO TRẠNG THÁI & KIẾN TRÚC HỆ THỐNG

```text
Project: P-153
Product: Enterprise Doc Intelligence Agent (NexaTech HR Policy Copilot)
Ngày báo cáo: 2026-08-22
Trạng thái: Engineering Audit
Nguồn sự thật: Source code + Database schema + Tests + Data
Repository Revision: 093a388 (branch develop)
```

> **Lưu ý metodology:** Toàn bộ nhận định trong report này được kiểm chứng trực tiếp
> từ source code, schema, migrations, data files, tests và scripts. Khi documentation
> mâu thuẫn với code, code được ưu tiên và documentation bị đánh dấu stale (mục 26).

---

# 1. TÓM TẮT ĐIỀU HÀNH

## 1.1 P-153 là gì?

P-153 là một **Agentic RAG copilot nội bộ bằng tiếng Việt** cho tenant "NexaTech"
(JWT auth, ACL theo Department + Role, hybrid retrieval, citation, escalation ticket),
đang **pivot** sang hướng **Enterprise Doc Intelligence**: trích xuất Structured
Knowledge (Knowledge Item / Evidence / Knowledge Relation) để phục vụ cross-document
reasoning có governance.

## 1.2 Product hiện tại làm được gì?

Đang chạy end-to-end (đã có tests + CI):

- **Frontend Next.js 15**: login/register, chat SSE streaming hiển thị citation
  (`[Nguồn N]`), ticket management, admin upload document + polling ingestion job,
  index rebuild, evaluation runs.
- **Backend FastAPI**: JWT self-issued, RBAC route-level, conversations, async chat
  requests có crash-recovery + idempotency, tickets, documents, proxy job sang Agent.
- **Agent Service (LangGraph)**: graph điều kiện thực tế — condense → router →
  boundary → retrieve → grade → rewrite → generate → hallucination_check →
  confidence → finalize | escalate_ticket.
- **Retrieval**: Hybrid (Dense Chroma + BM25 + RRF) + Reranker (bge-reranker-v2-m3),
  ACL **pre-filter** trong Chroma `where` clause (fail-closed).
- **Evaluation**: 25 datasets, 30+ scripts, 70+ result files thật, có bootstrap CI,
  Cohen's kappa; failed gates được ghi nhận trung thực.

## 1.3 Product mục tiêu là gì?

Theo `nexatech_agent_type_c_contract_v3.1.yaml` + `CHROMA_FINAL_BASELINE.md` (tài liệu
mới nhất, 2026-08-21): một **Enterprise Knowledge Governance & Reasoning System**:

```text
Document → Knowledge Extraction → Knowledge Items → Evidence → Relations
        → Cross-document Reasoning → Governed Answer → Citation → HITL → Audit
```

với contract 3 trạng thái đầu ra: ANSWER / ABSTAIN / OUT_OF_SCOPE (pháp định thuần
túy → nhất quyết từ chối, không retrieval).

## 1.4 Khoảng cách lớn nhất

**Lớp Structured Knowledge đang trống.** Schema đầy đủ (tenant-scoped) đã có trong
`src/knowledge/models.py` + `data/knowledge.db`, nhưng extractor hiện chỉ là
rule-based **cứng cho đúng 2 documents** (`src/knowledge/extractor.py:64,107`),
DB trống (0 rows ngoài tenant), không có caller nào ngoài module chính nó. Vì vậy
các điểm khác biệt của product — conflict detection, supersession, evidence chain,
cross-document reasoning — **chưa tồn tại khi chạy**. Hiện tại P-153 là một RAG
helpdesk được engineer tốt, chưa phải Doc Intelligence Agent.

## 1.5 Việc team cần ưu tiên ngay

**P0-A: Fix data-integrity ở write path Chroma** — live ingestion/indexing worker
đang ghi vào **static collection** và `delete_by_source_stem` **không truyền
`tenant_id`** (`src/workers/ingestion.py:105-107`, `src/workers/indexing.py:84`):
hai user upload trùng tên file ⇒ vector của người này **ghi đè/xóa** của người kia.

---

# 2. ĐỊNH NGHĨA PRODUCT

## 2.1 Bài toán

Nhân viên doanh nghiệp cần tra cứu chính sách nội bộ (HR, C&B, nghỉ phép, công tác
phí...) nhanh, có dẫn nguồn, kiểm soát được quyền truy cập theo phòng ban/vai trò.
Khó khăn: văn bản nằm rải rác nhiều định dạng (PDF scan, docx), trùng/lặp giữa các
phiên bản, một câu hỏi thường cần kết hợp nhiều văn bản, và **câu trả lời sai về
chính sách nội bộ có hậu quả pháp lý/điều hành thật**. Keyword search không hiểu
ngữ nghĩa đa ngôn ngữ (Việt/Anh), chatbot thường không có citation, không kiểm soát
được ai được thấy văn bản nào.

## 2.2 Người dùng

- **Employee** (role mặc định khi register — `backend/app/api/v1/auth.py`): hỏi
  chính sách, nhận answer + citation hoặc escalation ticket.
- **HR_ADMIN / SUPER_ADMIN**: upload document, quản lý metadata, index rebuild,
  chạy evaluation.
- (Thiết kế thêm: LEGAL_COUNSEL, MANAGER, EXECUTIVE... trong
  `config/access_policies.json`.)

## 2.3 Use cases

Chính: hỏi–đáp chính sách nội bộ có citation; escalation sang HR department
(C&B/ER/TA/L&D/HRBP) khi không tự trả lời được.
Phụ: upload & ingest document (admin); quản lý conversation; tra cứu citation
chi tiết; index rebuild; chạy evaluation runs; từ chối câu hỏi pháp định nhà nước
(Type C contract).

## 2.4 P-153 LÀ GÌ?

Kết hợp, theo trọng số thực tế trong code:

1. **Enterprise Agentic RAG** — phần lớn code đang chạy (graph, retrieval, citation).
2. **Enterprise Document Intelligence** — hướng đích (knowledge extraction, evidence,
   relations) — mới có vertical slice.
3. **Policy Governance System** — ACL, lifecycle, audit, HITL (một phần implemented,
   một phần designed).

## 2.5 P-153 KHÔNG PHẢI LÀ GÌ?

- **Không phải** chatbot pháp lý: contract Type C cấm trả lời luật nhà nước
  (BLLĐ, Nghị định...); LEGAL docs đang ở `PENDING_REVIEW`, bị loại khỏi
  retrieval production.
- **Không phải** hệ thống dữ liệu cá nhân/live: câu hỏi cần dữ liệu giao dịch
  realtime → ABSTAIN/escalate (boundary node).
- **Không phải** multi-tenant SaaS hoàn chỉnh: chỉ có 1 tenant thật (nexatech);
  tenant isolation ở **read path** là tốt, **write path** đang bypass (mục 9).
- **Không phải** Knowledge Graph sẵn sàng: relations/evidence chỉ là schema.

---

# 3. LỊCH SỬ VÀ SỰ THAY ĐỔI ĐỊNH HƯỚNG

```text
Định hướng cũ (README/ARCHITECTURE, ~15-19/08)
  "Doc Intelligence Agent VinBigData" tổng quát, có index corpus legal,
  collection "hr_documents"/"internal_docs"
      ↓
Product hiện tại (commit 093a388, 21-22/08)
  NexaTech internal-policy copilot, tenant_nexatech_knowledge đã dọn
  sạch LEGAL khỏi retrieval production, ACL Department+Role
      ↓
Định hướng mục tiêu (CHROMA_FINAL_BASELINE.md + src/knowledge/)
  Structured Knowledge Extraction & PostgreSQL modeling (Phase P1)
  → Reasoning → Governance
```

Bằng chứng pivot trong git log (6 commit gần nhất): `ebb2744` (GENERAL-only scope),
`647ca6b` (department-based legal domain auth), `1f447e0` (3-way classification
decoupling), `3f13a4c` (Department AND Role semantics + legal lifecycle),
`093a388` (Phase P1 vertical slice + Chroma baseline cleanup).

- **Thuộc architecture cũ**: description "generic doc agent" trong README,
  collection `hr_documents`/`internal_docs` trong ARCHITECTURE.md, việc index
  government legal docs (JOURNAL W2), taxonomy LLM cũ trong
  `scripts/classify_documents_llm.py`.
- **Thuộc architecture mới**: tenant collection naming
  (`src/security/tenant_resolver.py`), canonical registry 3-way
  (COMPANY_POLICY / DEPARTMENT_PROCESSES / LEGAL PENDING_REVIEW) trong
  `scripts/rag_pipeline/audit_and_classify_documents.py`, contract Type C,
  module `src/knowledge/`.
- **Documentation đang stale**: `README.md`, `ARCHITECTURE.md` (collection name,
  legal corpus, "frontend not built"), `JOURNAL.md`/`WORKLOG.md` dừng ở 19/08 —
  không cover 4 commit cuối. Chi tiết ở mục 26.

---

# 4. HỆ THỐNG HIỆN TẠI — END TO END

## 4.1 Query Flow (thực tế, theo code)

| Bước | Component | File | Function/Class | Input → Output | Vai trò |
|---|---|---|---|---|---|
| 1 | Frontend | `frontend/lib/api.ts` | `streamChatRequest` | question → SSE events | Gửi JWT, Idempotency-Key, nhận `answer_delta`/`citation` |
| 2 | Backend | `backend/app/api/v1/chat.py` | route handlers | Token → `get_current_user` dict (user_id, role, department) | Auth JWT (HS256), tạo `chat_requests` row (202 Accepted) |
| 3 | Backend | `backend/app/services/chat_service.py` | + `agent_answer_adapter` | user context + question → agent payload | Điều phối job async, persist kết quả |
| 4 | Agent | `src/api/routes.py` | `_verify_service_token` → `/agent/query/stream` | X-Service-Token | Service-to-service auth |
| 5 | Agent | `src/agents/graph.py` | `build_graph` | state → state | LangGraph orchestration |
| 6 | Agent | `src/agents/nodes/condense.py` | `condense_node` | history + question → standalone question | Multi-turn |
| 7 | Agent | `src/agents/nodes/router.py` | `router_node` + `_VERIFIER_SYSTEM` | question → intent (greeting/hr_question/ambiguous/out_of_scope_or_personal) | Intent detection |
| 8 | Agent | `src/agents/nodes/boundary.py` | boundary node | intent + question → scope decision (deterministic) | Chặn personal-data/statutory |
| 9 | Agent | `src/agents/nodes/retrieval.py` | `retrieval_node` | query + UserContext → chunks (ACL pre-filter) | Hybrid retrieval |
| 10 | Agent | `src/agents/nodes/retrieval.py` | `grade_node` / `rewrite_node` | chunks → keep/rewrite | Relevance threshold |
| 11 | Agent | `src/agents/nodes/generation.py` | `generate_node` | chunks + query → answer `[Nguồn N]` | Grounded generation (tiếng Việt) |
| 12 | Agent | `src/agents/nodes/generation.py` | hallucination check + `_check_numeric_grounding` | answer vs excerpts → PASS/FAIL | Faithfulness |
| 13 | Agent | `src/agents/nodes/escalation.py` | `confidence_node` | reranker score → confidence | Routing finalize/escalate |
| 14 | Agent | `src/agents/nodes/escalation.py` | `escalate_node` | → ticket draft | Escalation theo `ticket_routing_rules.json` |
| 15 | Backend | `tickets` service | — | ticket draft → Supabase `tickets` row | Persist escalation thật |

## 4.2 Document Ingestion Flow

**Offline pipeline (IMPLEMENTED)** — `scripts/rag_pipeline/`:

| Giai đoạn | File | Trạng thái |
|---|---|---|
| Parsing | `src/ingestion/extractors/documents.py::extract_document`, `pdf_vlm.py` (VLM cho PDF scan) | IMPLEMENTED |
| Cleaning | `src/ingestion/cleaners.py::clean_document` | IMPLEMENTED |
| Classification | `scripts/rag_pipeline/audit_and_classify_documents.py::build_canonical_registry()` — bảng audit **cứng** (10 COMPANY_POLICY / 9 DEPARTMENT_PROCESSES / 10 LEGAL PENDING_REVIEW / MANAGEMENT / EXTERNAL_REFERENCE) | PARTIALLY IMPLEMENTED — tồn tại song song taxonomy LLM cũ (`scripts/classify_documents_llm.py`) không dùng chung |
| Metadata | `src/ingestion/metadata.py::RegistryRow/load_registry` (CSV 31 field) | IMPLEMENTED |
| Chunking | `src/ingestion/chunkers.py` + `chunk_builder.py::build_chunks_from_text` (heading_path, frontmatter, tenant) | IMPLEMENTED |
| Embedding | `src/ingestion/embeddings.py::embed_texts` (FPT.AI, prefix `passage:`) | IMPLEMENTED |
| Indexing | `scripts/rag_pipeline/build_vector_db.py` — embed → `delete_by_source_stem` → upsert | IMPLEMENTED |
| Relational DB | `scripts/rag_pipeline/import_documents_to_supabase.py` — one-way sync CSV → `documents` (dashboard-only) | PARTIAL |

**Live ingestion (PARTIAL — có lỗ hổng)** — `src/workers/ingestion.py::run_ingestion`:
validate (extension + 25MB) → ghi `data/raw/uploads/` → extract → chunk (metadata do
backend cung cấp; **các field bảo mật `access_scope`/`authorized_*` không được truyền
⇒ default COMPANY_WIDE/ACTIVE**) → ghi `data/chunks/{stem}.json` → `_index_chunks`
ghi vào **static collection**, delete không tenant-scope, **cố ý không cập nhật
registry CSV** (docstring dòng 8-11). Hệ quả: document upload runtime **được index
nhưng không bao giờ retrieve được** — whitelist ACL chỉ đọc từ CSV
(`src/security/authorization.py::get_authorized_source_files`).

## 4.3 Answer Lifecycle

Question → persist `chat_requests` → agent stream: condense → router → boundary
(deterministic; greeting→direct, ambiguous→clarify, statutory→out_of_scope cố định
không LLM, personal→escalate) → retrieve (hybrid + ACL) → grade → (rewrite tối đa
`max_rewrite_retries`) → generate với citation → numeric grounding + hallucination
check (retry `max_hallucination_retries`) → confidence (từ reranker score) →
finalize (answer + citations + confidence persist vào messages/chat_requests, FE
hiển thị citation badge official/reference) **hoặc** escalate → ticket thật trong
Postgres → SSE `answer_delta`/`citation` events tới FE.

---

# 5. KIẾN TRÚC HỆ THỐNG

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Frontend | Next.js 15 + React 19 + TS | UI chat/citation/ticket/admin |
| Backend | FastAPI + SQLAlchemy async + Supabase Postgres | Auth, RBAC, state, durability |
| Agent Service | FastAPI + LangGraph | Graph, workers, retrieval |
| Vector DB | Chroma (Cloud prod / Persistent dev) | Dense retrieval |
| BM25 | `src/retrieval/bm25.py` | Lexical hybrid |
| LLM/Embed/Rerank | FPT.AI Marketplace (GLM-5.x, multilingual-e5-large, bge-reranker-v2-m3) | `models_config.json` |
| Workers | `src/workers/{ingestion,indexing,evaluation}.py` | Async jobs |
| Evaluation | `eval/` | Datasets + scripts + results |
| Auth | JWT self-issued + X-Service-Token | User + service |
| Authz | `src/security/` + RLS Supabase + ACL filter | Multi-layer |

```text
                         USER
                           │
                           ▼
        FRONTEND (Next.js — chat SSE, tickets, admin)
                           │  JWT (localStorage, auto-refresh 401)
                           ▼
        BACKEND FastAPI (/api/v1)
           │  auth.py · chat.py · conversations · tickets · documents
           │  RBAC route-level + per-user scoping + RLS
           │            │ X-Service-Token
           │            ▼
           │      AGENT SERVICE FastAPI (/api/v1/agent)
           │            │ LangGraph
           │   condense → router → boundary
           │        ├─ direct / clarify / out_of_scope (END)
           │        └─ retrieve → grade → rewrite ↺
           │                  → generate → hallucination_check
           │                  → confidence → finalize | escalate_ticket
           │            │
           │   ┌────────┼──────────────┬───────────────┐
           │   ▼        ▼              ▼               ▼
           │ Chroma   BM25+RRF    FPT.AI LLM      Supabase tickets
           │ (tenant collection, (rerank)      (generate/judge)  (escalation)
           │  ACL pre-filter)
           ▼
     Supabase Postgres (users, profiles, conversations, messages,
        chat_requests, documents, tickets, ingestion/index/eval jobs)
```

---

# 6. KIẾN TRÚC DỮ LIỆU

## 6.1 Raw Documents (`data/raw/`)

- **Tổng: ~51 documents** (51 processed .md ↔ 51 chunk .json khớp nhau).
- Nhóm: `company_regulations` (10, gồm 1 PDF thật VinFast), `compensation_policies`
  (6), `government_legal` (10 — luật thật: BLLĐ 2019, NĐ 145/2020, Luat BHXH 2024,
  NĐ 158/2025, thuế TNCN...), `leave_policies` (1), `onboarding_offboarding` (3),
  `recruitment_policies` (3, có PDF thật Vingroup/Base.vn), `synthetic_enterprise`
  (18 — prefix `bod_/eng_/fin_/hr_/it_/leg_/mgt_dec_/ops_/prc_/prd_/sec_`).
- Domain/department: HR (C&B, TA, ER, L&D), Legal, Finance, IT, Ops, Procurement,
  Product, Security, BoD.
- **Company-wide**: 10 docs COMPANY_POLICY (`access_scope=COMPANY_WIDE`).
- **Department-specific**: 9 docs DEPARTMENT_PROCESSES.
- **Legal/external**: 10 government docs — `PENDING_REVIEW`, bị loại khỏi
  retrieval production; nhóm EXTERNAL_REFERENCE (PDF thật bên thứ 3) — RESTRICTED,
  role-gated.
- **Rejected**: `data/rejected/` — **trống**.
- Lưu ý trung thực: corpus "chính thức NexaTech" phần lớn là **synthetic**
  (Review_128.md xác nhận; CHROMA_FINAL_BASELINE.md trình bày như official — xem mục 26).

## 6.2 Metadata (thực tế, `data/metadata/document_registry.csv` — 31 fields)

Các field then chốt (đã verify header thật):

| Field | Vai trò |
|---|---|
| `source_file` | Khóa nối chunk ↔ registry ↔ ACL whitelist |
| `document_domain` | COMPANY_POLICY / DEPARTMENT_PROCESSES / LEGAL... |
| `access_scope` | COMPANY_WIDE / DEPARTMENT / ROLE / PENDING_REVIEW / RESTRICTED |
| `authorized_departments` / `authorized_roles` | **Grant thật** cho RBAC (dept AND role) |
| `related_departments` | Chỉ semantic, **không** grant quyền |
| `authorization_status` / `authorization_source` | PENDING_REVIEW ⇒ deny (fail-closed) |
| `tenant` | Mặc định nexatech khi authority=tenant_official_policy |
| `publication_status` / `artifact_state` / `retrieval_enabled` | Lifecycle filter khi retrieve |
| `classification_confidence/status/reason` | Kết quả audit classification |
| `processed_path` / `chunks_path` / `indexed_at` | Vị trí artifact |

Không có trong registry: `user_id`, `document_id` (UUID chỉ có trong
`migration_document_map.json`), `effective_date`/`expiry_date`/`version` ở mức
registry (chỉ có trong frontmatter chunk và bảng `documents` Supabase).
`product_document_registry.csv` (20 fields) là registry song song cho corpus
product demo — **chưa tích hợp** với ACL chính.

## 6.3 Chunk (`data/chunks/*.json`)

- Chiến lược: chunk theo cấu hình target/max/min chars, giữ `heading_path`,
  ánh xạ page/sheet offset (`cleaners.page_for_offset`), parse frontmatter
  (title/document_code/version/owner/legal_basis/effective_date).
- **Chunk ID: `<source_stem>::<0000>`** — *không chứa tenant* (`chunk_builder.py:125`).
- `embedding_text` = `"passage: " + text` (chuẩn multilingual-e5).
- Metadata chunk mang đầy đủ linkage (source_file, domain, access_scope,
  authorized_*, tenant, issuer...) — dùng làm filter khi query.

## 6.4 Document Lifecycle

```text
Create (upload/import) → Extract → Classify → Index (Chroma) → Retrieve
  → Update → Version?? → Expire (expiry filter) → Archive/Soft-delete → Delete vectors?
```

**Gap:** không có Document Version model chạy thật (chỉ có bảng
`document_versions` trống trong knowledge.db); update = delete-by-stem + re-upsert
(nguy cơ mất dữ liệu nếu fail giữa chừng — không atomic); lifecycle filter khi
retrieve có (`effective_date_ymd <= now <= expiry_date_ymd`, active/frozen) nhưng
hiệu lực chỉ đúng với dữ liệu offline; live upload không vào registry ⇒ không có
lifecycle gì cả.

---

# 7. KIẾN TRÚC STORAGE

| Storage | Vai trò | Trạng thái | Nguồn |
|---|---|---|---|
| PostgreSQL (Supabase) | Users, profiles, conversations, messages, chat_requests, tickets, documents (dashboard), jobs; RLS | IMPLEMENTED (schema+RLS+ORM); `documents` là one-way sync | `supabase/migrations/0001-0007` |
| Chroma | Vector retrieval, tenant collection `tenant_nexatech_knowledge` | IMPLEMENTED (read path); write path live worker bypass tenant | `storage/vector_db/` (dev, 4,137 embeddings) / Chroma Cloud |
| CSV Registry | **ACL source of truth hiện tại** + lifecycle metadata | IMPLEMENTED nhưng là single point mâu thuẫn với DB | `data/metadata/document_registry.csv` |
| SQLite Knowledge DB | Schema P1: tenants/documents/versions/chunks/knowledge_items/relations/evidence | DESIGNED (1 tenant row, còn lại 0 rows) | `data/knowledge.db` |
| Raw Files | Gốc dữ liệu + uploads runtime | IMPLEMENTED | `data/raw/`, `data/raw/uploads/` |
| Backups | Snapshot JSON trước cleanup Chroma | IMPLEMENTED | `storage/backups/` (3 snapshots) |

> **System of Record hiện tại là gì?**
>
> - Vận hành chat/ticket/auth: **Supabase Postgres** (rõ ràng).
> - Truy cập & lifecycle document cho retrieval: **CSV Registry** — mâu thuẫn với
>   `documents` table (DB chỉ là bản sao dashboard). Đây là **conflict nguồn sự
>   thật** cần resolve (mục 22 P0-B).
> - Vector: Chroma (mất đồng bộ được phát hiện bằng audit script
>   `eval/scripts/audit_live_index_alignment.py`).

---

# 8. MULTI-TENANCY & AUTHORIZATION

- **Tenant model**: 1 tenant thật (`nexatech`), tenant_id truyền qua UserContext từ
  backend; collection naming `tenant_{tenant_id}_knowledge`
  (`src/security/tenant_resolver.py::get_tenant_collection_name`).
- **Tenant resolver**: `resolve_tenant_collection` — production thiếu tenant ⇒
  `PermissionError` (**fail-closed**); dev fallback `active_tenant` (fail-open ngoài
  production).
- **User identity**: JWT self-issued (`backend/app/core/security.py`) — claims chứa
  role/department; **không re-check DB mỗi request** (stale cho tới khi refresh
  token). Register cưỡng chế role=employee, department canonical.
- **Authorization engine** (`src/security/authorization.py::evaluate_access`), thứ tự:
  Admin bypass → chặn system/internal domains (EVALUATION_DATA, USER_PERSONA...) →
  EXTERNAL_REFERENCE role-gate → LEGAL default-deny (role ∈ policy hoặc dept ∈
  `departments_with_access` AND doc `authorized_departments`) → PENDING_REVIEW deny →
  RBAC COMPANY_WIDE/DEPARTMENT (**Department AND Role** — `authorized_departments` +
  `authorized_roles` là grant thật; `related_departments` không grant) → default
  False. Policy từ `config/access_policies.json`, fallback hard-coded fail-closed.
- **RLS**: migrations 0002/0003/0007 (profiles own-read, tickets assignee-or-admin,
  guard privilege...).
- **Chuỗi enforcement thực tế**:

```text
JWT auth (backend) → route RBAC (require_role) → service-level scoping
  → Agent: tenant resolver (collection) → AuthorizationEngine → allowed_files
  → Chroma where PRE-FILTER (trước vector search) → Rerank → LLM
```

> **Unauthorized document có thể lọt vào candidate retrieval không?**
> Dense: **KHÔNG** — `allowed_files` nằm trong `where` của `collection.query`
> (`src/agents/nodes/retrieval.py:73-98`); rỗng ⇒ `__NO_ACCESS__`.
> BM25: candidate thừa bị **post-filter** trước khi vào fusion (line ~263).
> **Tới Reranker?** Không. **Tới LLM?** Không. **Xuất hiện trong answer?** Không
> (generation bị giới hạn trong context block + numeric grounding check).
>
> Caveat: whitelist đến từ CSV ⇒ runtime-uploaded docs bị "invisible" (mọi người
> đều không thấy — fail-closed nhưng vỡ tính năng); `UserContext.from_state`
> default tenant=nexatech/EMPLOYEE khi thiếu state (`src/security/models.py:63-79`)
> — fail-open nếu caller quên truyền context (chỉ được cứu bằng PermissionError
> production của resolver).

---

# 9. CHROMA ARCHITECTURE

- **Collection naming**: `tenant_{tenant_id}_knowledge` (read path);
  config mặc định `chroma_collection_name = "tenant_nexatech_knowledge"` (`src/config.py:58`).
- **Client**: `src/ingestion/indexer.py::get_chroma_client` — CloudClient (prod) /
  PersistentClient (dev).
- **Vector IDs**: `chunk_id = f"{stem}::{idx:04d}"` — **không có tenant component**.
- **Upsert/delete**: `delete_by_source_stem(collection, stem, tenant_id=None)` —
  hỗ trợ tenant-scope **nhưng không caller nào truyền tenant_id** (dead parameter);
  mặc định delete theo `source_stem` trên toàn collection.
- **Reset**: `safe_delete_collection` chặn `--reset` khi thiếu
  `--allow-destructive-reset-DANGEROUS` và raise PermissionError trong production
  (guardrail P0-A tốt).
- **Re-index**: `src/workers/indexing.py` REPLACE/FULL/INCREMENTAL — REPLACE dùng
  delete-by-stem (không tenant).
- **Migration/cleanup**: cẩn thận — `migrate_to_tenant_collection.py`,
  `execute_chroma_cleanup.py` (12 phase, snapshot trước, delete theo ID list).

> **User A và User B upload document thì dữ liệu có thể ảnh hưởng lẫn nhau không?**
>
> **CÓ — ở write path runtime.**
>
> - **File/function**: `src/workers/ingestion.py::_index_chunks` (dòng 105-107) và
>   `src/workers/indexing.py::_reindex_one` (dòng 84): ghi vào
>   `settings.chroma_collection_name` (static) rồi
>   `delete_by_source_stem(collection, stem)` **không tenant**.
> - **Mechanism**: chunk ID chỉ theo `source_stem` ⇒ B upload file trùng stem với
>   A ⇒ vector của A bị xóa và thay bằng của B.
> - **Impact**: mất dữ liệu user khác âm thầm; sai answer; phá eval alignment.
> - **Severity**: **P0 — CRITICAL** (data corruption).
> - **Recommended fix**: route worker qua `resolve_tenant_collection`, luôn truyền
>   `tenant_id` vào `delete_by_source_stem`, thêm tenant vào chunk ID; test 2-tenant
>   chứng minh B không đụng được vector của A.
>
> Ngoài ra: file `scripts/migration/execute_chroma_cleanup.py:392` hardcode đường
> dẫn local `C:\Users\Lenovo\...` cho execution report (không portable).

---

# 10. AGENT ARCHITECTURE

| Node | Vai trò | Input | Output | Trạng thái |
|---|---|---|---|---|
| condense | Tạo câu hỏi standalone từ history | history + question | condensed question | IMPLEMENTED (trong graph) |
| router | Intent + verifier LLM | question | intent | IMPLEMENTED |
| boundary | Quyết định scope deterministic | intent + question | scope decision (personal/statutory/internal) | IMPLEMENTED |
| direct | Trả lời social talk | question | answer ngắn | IMPLEMENTED |
| clarify | Hỏi lại đúng 1 câu | ambiguous question | clarification | IMPLEMENTED |
| out_of_scope | Từ chối pháp định (template, không LLM) | statutory question | refusal cố định | IMPLEMENTED |
| retrieval | Hybrid retrieval ACL | query + UserContext | chunks | IMPLEMENTED |
| grade | Threshold relevance | chunks | keep/rewrite | IMPLEMENTED |
| rewrite | Viết lại query rồi retrieve lại | query | rewritten query | IMPLEMENTED |
| generation | Sinh answer grounded + citation | chunks + query | answer `[Nguồn N]` | IMPLEMENTED |
| hallucination check | Faithfulness PASS/FAIL | answer vs excerpts | pass/fail | IMPLEMENTED |
| confidence | Chấm confidence (reranker score) | rerank scores | confidence | IMPLEMENTED |
| escalation | Tạo ticket draft + persist | state | ticket | IMPLEMENTED |
| extraction | Trích xuất Decision/ActionItem | document | items | **DESIGNED — code có (`src/agents/nodes/extraction.py`) nhưng KHÔNG được add vào graph** |
| risk_hitl | Phân tầng rủi ro cho human review | answer | risk tier | **DESIGNED — có file, không wired (`src/agents/nodes/risk_hitl.py`)** |

## 10.1 CURRENT AGENT GRAPH (thực tế đang chạy)

```text
condense → router → boundary
  ├─ greeting          → direct (END)
  ├─ ambiguous         → clarify (END)
  ├─ pure statutory    → out_of_scope (END, fixed response)
  ├─ personal/live     → escalate_ticket (END)
  └─ hr_question       → retrieve → grade
                            ├─ có chunks (hoặc hết retry) → generate
                            └─ else → rewrite ↺ retrieve (tối đa max_rewrite_retries)
       generate → hallucination_check (retry generate tối đa max_hallucination_retries)
               → confidence
                   ├─ đạt ngưỡng → finalize (END)
                   └─ else → escalate_ticket (END)
```

## 10.2 TARGET AGENT GRAPH (sau P1/P2 — thiết kế)

```text
condense → router → boundary
  → retrieve (chunks + Knowledge Items)
  → grade → structured_reasoning (dựa trên Knowledge Relations)
  → generate (answer gắn Knowledge Item + Evidence)
  → hallucination_check → confidence
  → risk_hitl (PENDING_REVIEW khi rủi ro) → finalize | escalate_ticket
[Song song: ingestion → extraction_node → KnowledgeService → HITL review]
```

---

# 11. RETRIEVAL ARCHITECTURE

Thứ tự thực tế (`src/agents/nodes/retrieval.py`):

```text
Query condense/rewrite (_expand_retrieval_query — synonym expansion regex)
  → resolve_tenant_collection (fail-closed production)
  → embed query (FPT e5, cache)
  → DENSE: Chroma query với where PRE-FILTER:
        source_file ∈ allowed_files (AuthorizationEngine)
        AND publication_status="active" AND artifact_state="frozen"
        AND retrieval_enabled=True
        AND effective_date_ymd <= now <= expiry_date_ymd
        AND provenance ∉ synthetic_demo (production)
  → BM25 (per-collection; where chỉ lifecycle) — candidate thừa bị post-filter
    theo allowed_files trước khi vào chunk_map
  → Reciprocal Rank Fusion (src/retrieval/hybrid.py)
  → Reranker bge-reranker-v2-m3 (fail-open về dense order nếu lỗi)
  → grade_node: threshold theo rerank_min_score / retrieval_max_distance
      (không fallback top-3 — chủ đích design)
```

- **Authorization xảy ra TRƯỚC vector search** (dense pre-filter) — đây là điểm
  mạnh nhất của hệ thống hiện tại.
- Temporal filtering: có (effective/expiry trong where).
- Query rewrite: có (rewrite node + regex expansion).
- Điểm yếu chất lượng: held-out Recall@5 29.6% (gate 85%) — xem mục 18.

---

# 12. STRUCTURED KNOWLEDGE — CORE P1

## 12.1 Vì sao P-153 cần Structured Knowledge?

```text
RAG hiện tại:                      Doc Intelligence (target):
Document                           Document
 ↓                                    ↓
Chunk                              Knowledge Extraction (LLM)
 ↓                                    ↓
Retrieve                           Knowledge Items (facts/rules/deadlines)
 ↓                                    ↓
LLM                                Evidence (quote span + hash)
 ↓                                    ↓
Answer                             Relations (SUPERSEDES/CONFLICTS_WITH)
                                      ↓
                                    Reasoning (cross-document, temporal)
                                      ↓
                                    Governed Answer (audit được)
```

Khác biệt cốt lõi: RAG trả lời theo *văn bản được retrieve*; Doc Intelligence trả
lời theo *kiến thức đã cấu trúc, có nguồn gốc chứng minh được, có quan hệ giữa các
văn bản*. Chỉ khi có Knowledge Items + Relations thì hệ thống mới: (1) phát hiện
xung đột chính sách, (2) biết policy nào supersede policy nào theo thời gian,
(3) chứng minh được answer bắt nguồn từ đoạn văn gốc nào (evidence chain), (4) cho
con người review kiến thức trích xuất (HITL) trước khi nó ảnh hưởng answer. Đây là
**product differentiation** so với một chatbot RAG thông thường.

**Trạng thái repo:** schema + repository + resolver HOÀN CHỈNH trong `src/knowledge/`
(models.py, repository.py, resolver.py, service.py, database.py); extractor chỉ là
rule-based **cứng 2 documents** (`extract_knowledge_from_travel_policy`,
`extract_knowledge_from_mgt_dec_04`); DB trống; không có caller bên ngoài module.
⇒ **DESIGNED (vertical slice)**.

---

# 13. KNOWLEDGE ITEM

- **Định nghĩa (theo `src/knowledge/models.py`)**: một đơn vị kiến thức có cấu trúc
  — triple subject/predicate/object + numeric value + scope + effective dates +
  `review_status`, tenant-scoped, gắn với document version.
- **Schema bảng** `knowledge_items`: `knowledge_id, tenant_id, version_id,
  item_type, statement, structured_payload, confidence_score, review_status`.
- **Các loại item_type**: theo thiết kế extraction prompt (`src/agents/nodes/
  extraction.py::EXTRACTION_SYSTEM_PROMPT`) và `ground_truth_extractions.json`:
  decisions, action_items (task/responsible/deadline), rules, obligations...
- **Lifecycle thiết kế**: `AUTO_EXTRACTED → (HITL review) → APPROVED/REJECTED`.
- **CURRENT**: bảng tồn tại (SQLite, 0 rows); không có pipeline sinh item tổng quát.
- **TARGET**: extraction LLM chạy lúc ingest, persist theo tenant/document_version,
  confidence score, review workflow.
- **Ground truth cho đánh giá đã có sẵn**: `data/metadata/ground_truth_extractions.json`
  (decisions + action_items per doc + `cross_document_queries`).

## 14. EVIDENCE & PROVENANCE

- **Evidence record (thiết kế)** — `evidence_records`: `evidence_id, knowledge_id,
  chunk_id, page_number, section_heading, exact_quote_span, start_char, end_char,
  quote_hash`. Kèm `compute_sha256` + `find_quote_span` (`src/knowledge/extractor.py:48`,
  `repository.py`) — tức là bằng chứng **trỏ đúng khoảng ký tự** trong văn bản gốc,
  có hash chống sửa đổi.
- **Phân biệt**:
  - **Citation hiện tại (IMPLEMENTED)**: chunk được retrieve, hiển thị `[Nguồn N]`
    với badge official/reference, có trang detail citation — nhưng chỉ là chunk,
    không phải chuỗi provenance cấu trúc.
  - **Evidence record (DESIGNED)**: đối tượng độc lập, gắn Knowledge Item ↔
    document version ↔ đoạn trích gốc có hash — chuỗi chứng minh:

```text
Answer → Knowledge Item → Evidence → Document Version → Original Document
```

Hiện chuỗi này dừng ở "Answer → Chunk" (tức cited chunks thật, có grounding check,
nhưng chưa phải auditable evidence chain).

---

# 15. KNOWLEDGE RELATIONS

Schema (`knowledge_relations`): `relation_id, source_knowledge_id,
target_knowledge_id, relation_type, relation_payload, explanation,
confidence_score, detection_method`.
Các relation_type theo thiết kế: **SUPERSEDES, MODIFIES, IMPLEMENTS,
CONFLICTS_WITH, REFERENCES** (định nghĩa trong `src/knowledge/models.py`, được
CHROMA_FINAL_BASELINE.md tham chiếu là Phase P1).
Mỗi relation có explanation + confidence + detection_method (LLM/rule/hybrid).
**CURRENT: DESIGNED — không có code sinh relation, bảng 0 rows.**

---

# 16. CROSS-DOCUMENT REASONING

| Capability | Trạng thái | Evidence |
|---|---|---|
| Multi-document retrieval | IMPLEMENTED | retrieval trả nhiều chunks từ nhiều source_files |
| LLM synthesis trên nhiều chunks | IMPLEMENTED | generate_node nhận toàn bộ context block |
| Structured reasoning | MISSING | không có reasoning trên knowledge_items (DB trống) |
| Relation reasoning | MISSING | không có code đọc knowledge_relations |
| Conflict detection | MISSING | chỉ là relation_type trong schema |
| Supersession detection | MISSING | idem |
| Temporal reasoning | PARTIALLY IMPLEMENTED | temporal **filter** khi retrieve có (effective/expiry); temporal **reasoning** (phiên bản nào thắng) chưa có |

> Lưu ý: retrieve nhiều chunks rồi cho LLM tổng hợp **không phải** structured
> reasoning — đó vẫn là RAG synthesis.

---

# 17. HITL

- **Khi nào cần human review (thiết kế)**: knowledge item mới extract có
  `review_status=AUTO_EXTRACTED` cần duyệt; answer rủi ro cao (risk_hitl
  tiers); LEGAL docs PENDING_REVIEW chờ business decision.
- **Review status**: enum có trong `knowledge_items.review_status`.
- **Risk detection**: `src/agents/nodes/risk_hitl.py` tồn tại nhưng **không wired
  vào graph**.
- **Approval/rejection, API, UI**: **MISSING** — không có endpoint review, không có
  UI (frontend chỉ có chat/ticket/admin docs; Monitoring view là stub).
- Tóm lại: **DESIGNED**. (Eval tooling có `human_review_sample.json` nhưng đó là
  đánh giá, không phải HITL runtime.)

---

# 18. EVALUATION

- **Datasets (25 files, `eval/datasets/`)**: retrieval eval + qrels, QA set + held-out,
  guardrail sets, boundary set, condense multi-turn, router holdout, Type C contract
  set (TC-091..TC-110), human review sample.
- **Scripts (30+)**: `eval_retrieval.py`, `eval_agent.py`, `eval_guardrail.py`,
  `eval_router*.py`, A/B comparisons, `audit_live_index_alignment.py`,
  `profile_e2e.py`; thống kê thật trong `_stats.py` (bootstrap CI, paired bootstrap,
  Cohen's kappa).
- **Kết quả chính (không che giấu failed gates)**:

| Metric | Kết quả | Threshold | Pass/Fail |
|---|---|---|---|
| Router accuracy | 95.7% | — | PASS |
| QA eval (140 câu, legacy set) | 75.7% | — | PASS (nhưng legacy) |
| **Held-out agent eval 19/08** | **0/30** | — | **FAIL** |
| **Held-out Recall@5** | **29.6%** | **85% gate** | **FAIL** |
| p50 latency | ~35s (15-35s) | — | Cao (chưa streaming) |

- **Vấn đề dataset**: README thừa nhận legacy set mismatch; docs/report_2026-08-19.md
  có số tốt hơn nhiều (Hit@5 96.3%, MRR 0.849) nhưng trên dataset khác; qrel label
  noise được Review_128.md chỉ ra; eval 64-case từng bị block do 401 FPT key.
- **Kiểm thử**: ~45 test files (tests/) + backend tests: auth/RBAC, per-user
  isolation, chat durability (recovery, idempotency, concurrent 10-30 requests,
  crash restart), guardrails (PII redaction), ACL, type-C contract, migration parity.
  CI chạy ruff + pytest cho cả 2 service + dataset integrity check.

---

# 19. MA TRẬN TRẠNG THÁI IMPLEMENTATION

| Capability | Status | Evidence | Ghi chú |
|---|---|---|---|
| Authentication | IMPLEMENTED | `backend/app/core/security.py`, test_auth.py | JWT stale-role caveat |
| Authorization | IMPLEMENTED | `src/security/authorization.py`, pre-filter retrieval | Nguồn whitelist là CSV |
| Tenant isolation | PARTIALLY IMPLEMENTED | tenant_resolver (read) vs workers static collection (write) | P0-A |
| Ingestion (offline) | IMPLEMENTED | `scripts/rag_pipeline/` | |
| Ingestion (live) | PARTIALLY IMPLEMENTED | `src/workers/ingestion.py` | Không vào registry ⇒ unretrievable |
| Classification | PARTIALLY IMPLEMENTED | canonical registry cứng + taxonomy LLM cũ song song | |
| Chunking | IMPLEMENTED | `chunkers.py`, `chunk_builder.py` | |
| Embedding | IMPLEMENTED | `embeddings.py` (FPT e5) | |
| Retrieval | IMPLEMENTED | hybrid + pre-filter ACL | Chất lượng held-out FAIL gate |
| Reranking | IMPLEMENTED | bge-reranker-v2-m3, fail-open | |
| Citation | IMPLEMENTED | generation + citations API + FE | Chunk-level, chưa phải Evidence |
| Knowledge Extraction | DESIGNED | `src/knowledge/extractor.py` (2 docs cứng) | Vertical slice |
| Knowledge Item | DESIGNED | `knowledge.db` 0 rows | |
| Evidence | DESIGNED | `evidence_records` schema + hash/span helpers | |
| Relations | DESIGNED | `knowledge_relations` schema | |
| Cross-document Reasoning | MISSING | không code | |
| HITL | DESIGNED | review_status + risk_hitl node unwired | |
| Governance | PARTIALLY IMPLEMENTED | RLS, ticket closure audit, llm_trace.py | Không có AuditLog table |
| Evaluation | IMPLEMENTED | eval/ đầy đủ, failed gates ghi nhận trung thực | Dataset noise |
| CI/CD | PARTIALLY IMPLEMENTED | `.github/workflows/ci.yml` (lint+test) | Không deploy pipeline |

---

# 20. CRITICAL ISSUES & RISKS

| ID | Severity | Vấn đề | Impact | Component | Hành động |
|---|---|---|---|---|---|
| R-01 | P0-CRITICAL | Live worker ghi static collection + `delete_by_source_stem` không tenant_id; chunk ID không tenant | User B xóa/ghi đè vector User A khi trùng stem | `src/workers/ingestion.py:105`, `indexing.py:84`, `chunk_builder.py:125` | Tenant-resolve + truyền tenant_id + tenant trong ID + test 2-tenant |
| R-02 | P0 | Runtime upload không vào ACL registry ⇒ unretrievable; metadata security default COMPANY_WIDE | Tính năng upload silently broken; nếu sau này nối registry sẽ lộ scope sai | `src/workers/ingestion.py`, `authorization.py::get_authorized_source_files` | Thống nhất ACL source of truth (Postgres) |
| R-03 | P0 | Fail-open ngoài production: `UserContext.from_state` default tenant/role; dev fallback resolver | Lộ dữ liệu nếu chạy non-prod với dữ liệu thật | `src/security/models.py:63-79`, tenant_resolver | Bỏ default, bắt buộc context |
| R-04 | P1 | JWT không re-check role/department theo DB mỗi request | Quyền stale sau khi đổi role | `backend/app/api/dependencies/auth_deps.py` | Re-verify từ profiles |
| R-05 | P1 | Structured Knowledge: extractor 2-doc cứng, DB trống, không caller | Product target không thể đạt nếu không generalize | `src/knowledge/` | LLM extraction pipeline (mục 22 P1) |
| R-06 | P1 | Held-out gate FAIL (agent 0/30, Recall@5 29.6%<85%) | Chất lượng answer chưa đạt cam kết | eval/datasets | Fix dataset noise + retrieval |
| R-07 | P2 | Documentation stale/mâu thuẫn (README, ARCHITECTURE, JOURNAL) | Engineer mới hiểu sai hệ thống | mục 26 | UPDATE/ARCHIVE |
| R-08 | P2 | Hardcode path `C:\Users\Lenovo\...` trong cleanup script; `backend/test_temp.db*` committed | Không portable, bẩn repo | `execute_chroma_cleanup.py:392` | Config hóa + gitignore |
| R-09 | P2 | Monitoring view FE stub; không có HITL UI | UX/admin gap | `frontend/components/HrKnowledgeApp.tsx:83-85` | Wire sau P1 |

---

# 21. CURRENT → TARGET GAP

| Thành phần | CURRENT | TARGET | GAP |
|---|---|---|---|
| Retrieval | Hybrid + rerank + ACL pre-filter, held-out FAIL gate | Retrieval chất lượng cao + cả Knowledge Items | Fix gate + integrate knowledge |
| Knowledge | Schema + 2-doc slice, DB trống | LLM extraction toàn corpus, persist Postgres | Toàn bộ pipeline extraction |
| Evidence | Chunk citation | Evidence record (span+hash) gắn Knowledge Item | Model + persistence + wiring |
| Relations | Enum trong schema | Sinh + lưu + query SUPERSEDES/CONFLICTS_WITH | Detection pipeline |
| Reasoning | RAG synthesis | Structured cross-document reasoning | Reasoning layer |
| HITL | review_status column + node unwired | Review workflow API + UI | API + UI + graph wiring |
| Governance | RLS + ticket audit + trace | AuditLog, evidence chain, approval trail | Bảng audit + policy |
| Security | ACL read mạnh; write path P0 hole | Tenant-safe toàn đường | Fix R-01..R-03 |
| Evaluation | Phạm vi rộng, trung thực | Thêm extraction/relation eval + passed gates | Eval cho P1 + đạt gate |

---

# 22. ROADMAP TIẾP THEO

## P0 — Stabilization

1. **Tenant-safe indexing** — Objective: không user nào ảnh hưởng vector user khác.
   Files: `src/workers/ingestion.py`, `src/workers/indexing.py`,
   `src/ingestion/indexer.py`, `chunk_builder.py`. Dependency: không có (làm ngay).
   Order: đầu tiên. Acceptance: test 2 tenant × upload trùng stem ⇒ vector tách biệt;
   production không còn caller nào của `delete_by_source_stem` thiếu tenant_id.
2. **ACL source of truth thống nhất** — Objective: runtime upload retrievable và
   authorize đúng. Files: `src/security/authorization.py`, `src/workers/ingestion.py`,
   Supabase `documents`. Dependency: sau (1) để tránh index vào nơi sai. Acceptance:
   upload e2e test: doc được retrieve bởi người có quyền, bị chặn với người không.

## P1 — Structured Knowledge

3. **Generic LLM Knowledge Extraction** — thay extractor cứng bằng LLM (prompt nền
   từ `EXTRACTION_SYSTEM_PROMPT`), chạy lúc ingest, ghi `knowledge_items` +
   `evidence_records` (span+hash), `review_status=AUTO_EXTRACTED`. Files:
   `src/knowledge/extractor.py`, `src/workers/ingestion.py`, `src/knowledge/service.py`.
   Dependency: P0 xong (data đúng trước khi extract). Acceptance: chạy trên ≥ 10
   docs thật, so với `ground_truth_extractions.json`, F1 ≥ ngưỡng team chốt.
4. **Relation Detection** (SUPERSEDES/CONFLICTS_WITH/REFERENCES) trên items đã lưu.
   Dependency: (3). Acceptance: ≥ 1 cặp SUPERSEDES/CONFLICT được phát hiện đúng từ
   corpus synthetic có mgt_dec versions.
5. **Wire extraction/risk_hitl + HITL review API tối tiểu**. Dependency: (3).

## P2 — Reasoning & Governance

6. Reasoning node dùng Knowledge Items + Relations trong answer (graph target 10.2);
   conflict-aware answers. 7. HITL UI + AuditLog table. 8. Fix held-out retrieval
   gate (dataset noise + hybrid tuning). 9. Monitoring view FE.

## P3 — Production Maturity

10. Deploy pipeline, observability production, load/stability, cleanup repo
    (R-08), doc consolidation.

---

# 23. THỨ TỰ IMPLEMENTATION KHUYẾN NGHỊ

```text
1. Fix tenant-safe indexing (R-01)
      ↓  (vector đúng trước — mọi thứ sau này đọc/ghi Chroma)
2. Fix ACL source of truth (R-02)
      ↓  (doc không retrievable thì extraction cũng vô dụng)
3. Stabilize Document/Version model trong Postgres
      ↓  (Knowledge Item cần FK version_id ổn định)
4. Generic Knowledge Extraction (LLM)
      ↓  (Knowledge Items là đầu vào của Evidence + Relations)
5. Persist Evidence (span + hash)
      ↓  (Evidence do extraction sinh ra cùng lúc)
6. Relation Detection
      ↓  (Relations nối các items đã tồn tại)
7. Cross-document Reasoning
      ↓  (Reasoning tiêu thụ items + relations)
8. HITL
      ↓  (Review từng nhận knowledge/answer rủi ro)
9. End-to-end Evaluation cho P1
```

Lý do thứ tự: đây là dependency chain thực tế từ repo — extraction (4) cần model
document/version ổn (3) và dữ liệu index đúng (1,2); relations (6) về mặt logic
không thể tồn tại trước items (4); reasoning (7) cần cả items lẫn relations; HITL
(8) chỉ có ý nghĩa khi có kiến thức để review; evaluation (9)kiểm chứng toàn chuỗi.

---

# 24. MINIMUM P1 VERTICAL SLICE

```text
Document
 ↓ Structured Extraction (LLM, generic)
 ↓ Knowledge Item (Postgres/knowledge DB, tenant-scoped)
 ↓ Evidence (quote span + SHA256)
 ↓ Relation (SUPERSEDES giữa 2 phiên bản)
 ↓ Reasoning (answer ưu tiên item effective mới nhất)
 ↓ Answer + Citation trỏ Evidence
```

**Scenario 2 documents (đã có sẵn data):** `mgt_dec_04` (Q3 financial cap) và một
`mgt_dec` sau đó supersede nó (corpus synthetic có `mgt_dec_01..06`).

```text
Document A (mgt_dec_04)  +  Document B (mgt_dec mới hơn)
      ↓ Relation SUPERSEDES (có evidence 2 phía)
      ↓ Cross-document reasoning: chọn quy định effective tại thời điểm hỏi
      ↓ Answer: "Hiện tại áp dụng B (hiệu lực dd/mm), trước đó là A — [Evidence E1, E2]"
```

**Acceptance Criteria:**
1. Cả 2 documents được extract tự động (không hardcode) thành items + evidence;
   span hash khớp văn bản gốc.
2. Relation SUPERSEDES được detect và lưu kèm evidence + confidence.
3. Câu hỏi về hạn mức áp dụng hiện tại trả về answer dựa trên item effective,
   citation trỏ được về evidence span của đúng document.
4. Câu hỏi về thời điểm trước effective_date của B trả lời theo A (temporal).
5. Tenant/user không có quyền với 1 trong 2 docs không thấy evidence doc đó.
6. Test tự động cover 1-5 trong CI.

---

# 25. FILE / MODULE MAP

| Module | Vai trò | Status | Được sử dụng bởi |
|---|---|---|---|
| **Frontend** | | | |
| `frontend/components/ChatView.tsx` | Chat SSE + citation UI | IMPLEMENTED | HrKnowledgeApp |
| `frontend/components/TicketsView.tsx`, `KnowledgeAdmin.tsx`, `LoginView.tsx` | Ticket/Admin/Auth UI | IMPLEMENTED | HrKnowledgeApp |
| `frontend/lib/api.ts` | API client (JWT refresh, idempotency) | IMPLEMENTED | mọi view |
| **Backend** | | | |
| `backend/app/api/v1/*` | 9 routers (auth, chat, conversations, citations, tickets, documents, ingestion, indexes, evaluation) | IMPLEMENTED | FE |
| `backend/app/core/security.py`, `dependencies/auth_deps.py` | JWT + RBAC | IMPLEMENTED | routers |
| `backend/app/services/*` | chat durability, ticket, document, worker_job_client | IMPLEMENTED | routers |
| **Agent** | | | |
| `src/agents/graph.py` | LangGraph build | IMPLEMENTED | routes.py |
| `src/agents/nodes/*` | 11 node chạy + 2 node unwired | IMPLEMENTED/DESIGNED | graph |
| `src/agents/guardrails.py` | strip/redact PII, injection detect | IMPLEMENTED | query path |
| **Ingestion** | | | |
| `src/ingestion/{extractors,cleaners,chunkers,chunk_builder,metadata,embeddings,indexer}.py` | Pipeline core | IMPLEMENTED | scripts + workers |
| `src/workers/{ingestion,indexing,evaluation}.py` | Runtime jobs | PARTIAL (P0 holes) | agent routes |
| **Retrieval** | | | |
| `src/agents/nodes/retrieval.py` | Hybrid + ACL | IMPLEMENTED | graph |
| `src/retrieval/{bm25,hybrid,cache}.py` | BM25/RRF/cache | IMPLEMENTED | retrieval node |
| **Security** | | | |
| `src/security/{tenant_resolver,authorization,models}.py` | Tenant + ACL | IMPLEMENTED | retrieval/workers |
| **Knowledge (P1)** | | | |
| `src/knowledge/{models,repository,resolver,service,extractor,database}.py` | Schema + 2-doc slice | DESIGNED | chưa có caller |
| **Evaluation** | | | |
| `eval/datasets`, `eval/scripts`, `eval/results` | Đánh giá toàn diện | IMPLEMENTED | CI + manual |
| **Database** | | | |
| `supabase/migrations/0001-0007` | Schema + RLS + hr registry | IMPLEMENTED | backend |
| **Scripts** | | | |
| `scripts/rag_pipeline/*` | Offline pipeline + guarded reset | IMPLEMENTED | ops |
| `scripts/migration/*` | Chroma migration/cleanup | IMPLEMENTED (cẩn thận) | ops |
| `scripts/knowledge/init_knowledge_db.py` | Tạo knowledge tables | IMPLEMENTED | ops |

---

# 26. DOCUMENTATION DEBT

| Document | Vấn đề | Trạng thái | Hành động đề xuất |
|---|---|---|---|
| `ARCHITECTURE.md` | Collection `hr_documents` + diagram `internal_docs` (thực tế `tenant_nexatech_knowledge`); nói legal được index; "frontend not built" | STALE | UPDATE |
| `README.md` | Định hướng VinBigData generic; metrics trên legacy dataset; deliverables advanced chưa có | STALE | UPDATE |
| `JOURNAL.md` / `WORKLOG.md` | Dừng 19/08, không cover 4 commit pivot cuối | STALE | UPDATE |
| `CHROMA_FINAL_BASELINE.md` | Gọi corpus synthetic là "NexaTech official"; định nghĩa P1 khác P0/P1/P2 của PM_review | MISMATCHED FRAMING | UPDATE (làm rõ nguồn synthetic) |
| `PM_review.md` / `Review_128.md` | Chu kỳ review cũ, nhiều phát hiện đã fix | HISTORICAL | ARCHIVE |
| `Contract_Boundary_128.md` | Department taxonomy cũ (5 dept) lệch seed mới (11 dept) | PARTIALLY STALE | MERGE vào contract yaml |
| `docs/project/hr_physical_schema_and_knowledge_spec.md` | Nói "chưa code" nhưng `src/knowledge/` đã có | STALE | UPDATE |
| `report_1208.md`, `report_demo_1108.md`, `Review_128.md` | Snapshot cũ | HISTORICAL | ARCHIVE |

*(Không file nào trong mục này bị sửa bởi task hiện tại.)*

---

# 27. ARCHITECTURAL DECISIONS

| Decision | Rationale | Evidence | Confidence |
|---|---|---|---|
| Tenant-per-collection trong Chroma | Isolation READ rõ ràng, filter đơn giản | `tenant_resolver.py`, `tenant_nexatech_knowledge` | CAO (đã quyết, read path chạy) |
| PostgreSQL cho structured state, Chroma cho vector | Đúng vai trò từng storage; jobs/audit cần transactional | migrations, worker jobs | CAO |
| ACL pre-filter trong Chroma `where` (fail-closed) | Chặn unauthorized TRƯỚC vector search, không leak qua reranker/LLM | `retrieval.py:73-98` | CAO |
| Department AND Role làm grant (related_departments chỉ semantic) | Ngăn quyền truy cập gián tiếp không chủ đích | `authorization.py`, commit 3f13a4c | CAO |
| LEGAL = PENDING_REVIEW, không answer pháp định (Type C) | Tránh rủi ro pháp lý; contract yaml cấm | contract v3.1, baseline doc | CAO |
| Evidence = quote span + SHA256 | Chống sửa đổi, audit được | `knowledge/repository.py`, models | CAO (đã chốt thiết kế) |
| Knowledge Relations (SUPERSEDES/CONFLICTS_WITH/...) | Nền tảng cross-document reasoning | models.py | CAO (thiết kế) |
| HITL qua review_status | Kiểm soát kiến thức trước khi ảnh hưởng answer | models.py | TRUNG BÌNH (chưa wire) |
| Extraction dùng LLM hay rule-based | — | chỉ có rule-based 2-doc | **UNKNOWN** — team chưa chốt |
| CSV Registry giữ hay retire | — | đang là ACL source of truth nhưng conflict với DB | **UNKNOWN** — mục 28 |

---

# 28. OPEN QUESTIONS

1. PostgreSQL có trở thành System of Record duy nhất (kể cả ACL/lifecycle),
   hay CSV Registry giữ vai trò gì? (liên quan trực tiếp R-02)
2. Collection-per-tenant có phải kiến trúc chính thức multi-tenant, hay product
   chỉ single-tenant NexaTech? (quyết định đầu tư resolver+workers)
3. Knowledge DB: SQLite (`data/knowledge.db`) là chỗ thử nghiệm hay sẽ chuyển
   schema này vào Supabase Postgres? (hiện đang song song 2 nơi)
4. Knowledge Item taxonomy chính thức là gì (decisions/action_items/rules/
   obligations...)? Ground truth JSON và extraction prompt đang không đồng bộ.
5. Relation detection: LLM, rule-based hay hybrid? Confidence threshold?
6. Knowledge nào bắt buộc HITL trước khi dùng trong answer?
7. Reasoning nằm ở Agent layer (graph node) hay Knowledge layer (query API)?
8. Extraction accuracy target là bao nhiêu để được coi "đủ dùng" cho P1 gate?
9. Corpus product (`product_document_registry.csv`) tích hợp vào ACL chính thế nào?
10. Streaming output cho FE (giảm p50 35s) — ưu tiên khi nào?

---

# 29. TEAM HANDOFF

## Nếu một engineer mới tham gia P-153 ngày mai

1. **Project là gì**: Agentic RAG copilot chính sách nội bộ NexaTech, đang pivot
   sang Doc Intelligence (structured knowledge).
2. **Product hiện tại**: chat có citation + ACL + escalation ticket + admin upload
   (nhưng upload runtime chưa retrievable — biết trước để không mất thời gian debug).
3. **Product mục tiêu**: xem mục 1.3 + contract yaml + CHROMA_FINAL_BASELINE.md.
4. **Đang chạy**: 2 service FastAPI (`backend/`, `src/`) + Next.js FE; docker-compose.
5. **Đang lỗi**: R-01 (Chroma write path), R-02 (upload unretrievable), held-out
   eval gate FAIL.
6. **Không được sửa/xóa tùy tiện**: `safe_delete_collection` guardrail,
   `execute_chroma_cleanup.py` (script production đã chạy), registry CSV (là ACL
   source of truth hiện tại — sửa sai là mất quyền truy cập toàn hệ thống),
   snapshots trong `storage/backups/`.
7. **P0 hiện tại**: mục 22 P0 (tenant-safe indexing, ACL source of truth).
8. **P1 phải xây**: structured knowledge pipeline (mục 22 P1).
9. **Module quan trọng**: xem bảng mục 25.
10. **Recommended Reading Order**:
    1. `docs/PROJECT_STATUS_REPORT.md` (file này)
    2. `nexatech_agent_type_c_contract_v3.1.yaml` (contract hành vi)
    3. `src/agents/graph.py` + `src/agents/nodes/retrieval.py` (tim hệ thống)
    4. `src/security/{tenant_resolver,authorization}.py` (security model)
    5. `data/metadata/document_registry.csv` (ACL thật)
    6. `src/workers/ingestion.py` (biết P0 hole ở đâu)
    7. `src/knowledge/models.py` (target schema P1)
    8. `CHROMA_FINAL_BASELINE.md` (trạng thái vector production)
    9. `eval/` (datasets + failed gates)
    10. `frontend/lib/api.ts` + `ChatView.tsx` (FE contract)

---

# 30. ONE-PAGE TEAM SUMMARY

```text
PROJECT:
P-153

CURRENT PRODUCT:
Agentic RAG copilot chính sách nội bộ NexaTech (tiếng Việt): JWT auth,
ACL Department+Role pre-filter, hybrid retrieval + reranking, citation
grounded, escalation ticket, admin ingestion, eval harness đầy đủ.

TARGET PRODUCT:
Enterprise Doc Intelligence Agent: Document → Knowledge Extraction →
Knowledge Items + Evidence (span+hash) → Relations → Cross-document
Reasoning → Governed Answer → HITL → Audit.

CURRENT STRENGTHS:
- Security read-path xuất sắc: fail-closed tenant resolver, ACL pre-filter
  trước vector search, BM25 post-filter, RLS Supabase, guardrails PII.
- LangGraph thật (grade/rewrite/hallucination-retry/confidence/escalate)
  + chat durability (recovery, idempotency) được test kỹ.
- Evaluation framework nghiêm túc với failed gates được ghi nhận trung thực.
- Schema P1 (knowledge/relations/evidence) thiết kế chỉn chu, tenant-scoped.

CURRENT BLOCKERS:
- Live ingestion ghi static Chroma collection, delete không tenant_id
  (user có thể ghi đè vector nhau) — R-01.
- Runtime upload không vào ACL registry ⇒ document upload không bao giờ
  được retrieve — R-02.
- Structured knowledge: extractor cứng 2 documents, DB trống.
- Held-out eval gate FAIL (agent 0/30, Recall@5 29.6% < 85%).

BIGGEST ARCHITECTURAL GAP:
Không có lớp Structured Knowledge chạy thật — mọi năng lực khác biệt của
product (conflict detection, supersession, evidence chain, cross-document
reasoning, HITL) đều phụ thuộc lớp này và hiện chỉ tồn tại dưới dạng schema.

P0:
- Tenant-safe indexing (workers + chunk ID + delete tenant-scope).
- Thống nhất ACL source of truth (registry CSV → Postgres); upload retrievable.
- Bỏ fail-open defaults (UserContext, dev fallback).

P1:
- Generic LLM Knowledge Extraction → Knowledge Items + Evidence.
- Relation Detection (SUPERSEDES/CONFLICTS_WITH).
- Wire extraction/risk_hitl vào graph + HITL review API tối tiểu.

P2:
- Cross-document reasoning trên knowledge graph; conflict-aware answers.
- HITL UI; AuditLog; fix held-out retrieval gate; Monitoring view.

NEXT ENGINEERING MILESTONE:
Vertical slice P1 (mục 24): 2 documents mgt_dec → extraction tự động →
SUPERSEDES relation → temporal evidence-backed answer, có test trong CI.

DEFINITION OF DONE:
1) Không caller nào delete vector thiếu tenant-scope; test 2-tenant xanh.
2) Upload runtime retrievable đúng ACL (e2e test).
3) Slice P1 đạt 6 acceptance criteria mục 24 trong CI.
4) Held-out gate đạt ngưỡng team chốt hoặc có kế hoạch fix dataset có sign-off.
```
