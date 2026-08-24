# PRODUCT CONTENT AUDIT — Frontend P-153 HR Knowledge — 2026-08-23

```text
Phạm vi:      Toàn bộ frontend/ (8 components + lib + layout) và trace FE ↔ BE contract
              cho các claim về AI/RAG/documents/ticket/permission.
Nguồn truth:  README.md, ARCHITECTURE.md, PILOT_READINESS_IMPLEMENTATION_PLAN_20260823.md,
              docs/UX_PERSONA_QC_REPORT_20260822.md, backend/app/**, src/workers/**,
              qa/audit_20260823/data/live_matrix_runs.json (30 run live cùng ngày).
Nguyên tắc:   UI hiện tại KHÔNG là source of truth. Mọi finding có evidence file:line.
```

---

## A. PRODUCT UNDERSTANDING (từ spec, không từ UI)

- **Định vị:** Doc Intelligence Agent (P-153) — AI Agent RAG trả lời/tóm tắt/trích xuất tri thức
  từ kho tài liệu nội bộ, 100% câu trả lời nghiệp vụ phải có citation kiểm chứng được,
  zero-hallucination tolerance. Pilot branding FE: "HR Knowledge — Trợ lý AI HR".
- **Core users:** Nhân viên (tra cứu, hỏi đáp) và Quản trị tri thức (upload, quản lý kho).
- **Core use cases:** hỏi đáp có trích dẫn; từ chối khi thiếu bằng chứng (không bịa);
  ticket hỗ trợ HR; upload → ingest → index → hỏi được ngay; RBAC + phân quyền theo phòng ban.
- **Runtime thật hiện nay (code-verified):**
  - Worker ingestion/indexing/evaluation **đã triển khai và chạy E2E** (`src/workers/*.py`,
    E2E P1a–P5 PASS — plan mục 1.4-1).
  - Agent **luôn gửi `boundary`** trong AgentAnswer (Runtime-Revised Canonical Scenario
    Registry). Theo `backend/app/services/agent_answer_adapter.py:28-45`, hễ có `boundary`
    thì backend **KHÔNG tự tạo ticket** từ lượt chat (MVP-1). Chỉ đường legacy (agent cũ
    không gửi boundary) mới ghi ticket. `src/models/schemas.py:321-328` xác nhận cùng điều.
  - Corpus hiện tại là **dữ liệu mô phỏng NexaTech** (`provenance: "synthetic_demo"`,
    `source_type: "synthetic"` — live_matrix_runs.json; FE đã gắn nhãn "Dữ liệu mô phỏng").

## B. CONTENT AUDIT FINDINGS

### P0 — Sai sự thật về hệ thống (UI phủ nhận năng lực thật của sản phẩm)

| ID | Location | Current Content | Problem | Expected | Evidence |
|----|----------|-----------------|---------|----------|----------|
| C-01 | `KnowledgeAdmin.tsx:57` | "Upload tạm khóa — Backend hiện chỉ tạo metadata và job QUEUED; worker trích xuất/chunk/index chưa được triển khai." | **Sai sự thật**: worker đã triển khai, pipeline upload→extract→chunk→embed→Chroma chạy E2E (P1a–P5 PASS). Panel chặn toàn bộ persona Knowledge Admin và phát biểu sai về sản phẩm. | Upload UI thật gọi `api.uploadDocument` + poll `getIngestionJob` (api client đã có sẵn `api.ts:336-346`, CSS `.upload-panel` đã có sẵn). | `src/workers/ingestion.py:120-202`, `src/workers/jobs.py`, plan 1.4-1, backend `document_service.py:50-188` |
| C-02 | `KnowledgeAdmin.tsx:70-71` | "Contract API đã có nhưng Backend chưa có worker thực thi" / "Re-index hiện chỉ tạo job QUEUED và chưa xử lý Vector Store" / "Evaluation… chưa chạy dataset thật" | **Sai sự thật** với cả index rebuild lẫn evaluation worker. | Wire UI thật: `startIndexRebuild/getIndexRebuild`, `startEvaluation/getEvaluation` (api client có đủ `api.ts:347-360`). | `src/workers/indexing.py:105-167`, `src/workers/evaluation.py`, backend `indexes.py`, `evaluation.py` |

### P1 — Gây hiểu sai hành vi hệ thống / overclaim

| ID | Location | Current Content | Problem | Expected | Evidence |
|----|----------|-----------------|---------|----------|----------|
| C-03 | `ChatView.tsx:575` | "Yêu cầu không đủ bằng chứng **có thể đã được Backend chuyển thành ticket** theo kết quả Agent." | **Sai ở runtime hiện tại**: agent luôn gửi `boundary` → adapter `blocks_workflow_creation()` luôn True → 0 ticket được tạo từ chat. Nhân viên chờ HR liên hệ sẽ không ai xử lý (QC BUG-03/UX-04, xác nhận ở code). | Câu đúng thực tế + hướng hành động: chưa đủ bằng chứng trong kho → gợi ý tạo ticket thủ công (tính năng có sẵn). | `agent_answer_adapter.py:28-45`, `src/models/schemas.py:321-328`, `chat_service.py:338-345` |
| C-04 | `LoginView.tsx:61` | Trust badge "Nguồn tin cậy — **Chính sách được phê duyệt**" | Overclaim: corpus hiện là dữ liệu mô phỏng (`synthetic_demo`); ARCHITECTURE yêu cầu cảnh báo khi nguồn là synthetic để nhân viên không hiểu là chính sách chính thức. Badge đăng nhập khẳng định ngược. | Hứa đúng năng lực thật: câu trả lời kèm trích dẫn nguồn để đối soát (không khẳng định "được phê duyệt"). | ARCHITECTURE.md mục Security (cờ `is_official_policy`), live_matrix_runs.json `provenance:"synthetic_demo"` |
| C-05 | Nhiều nơi (liệt kê dưới) | Enum thô hiện trực tiếp: `INSUFFICIENT_EVIDENCE`, `ANSWERED`, `QUEUED/RETRIEVING/GENERATING`, `ACTIVE/ENDED`, `EMPLOYEE/HR_ADMIN` (sidebar user), `ingestion_state`, `INDEXED/PENDING`, `ACTIVE/ARCHIVED` (filter + bảng), `escalate_reason` (`user_requested_human`) | Terminology developer thay vì user; New-user persona không decode được; QC UX-03 đã flag. | Bảng map tập trung `lib/labels.ts`, mọi điểm hiển thị dùng label tiếng Việt. | QC report UX-03/UX-09; `types.ts:92-101`, `TicketItem.escalate_reason`, `ticket_service.py:98-100` |

Điểm hiện enum thô: `ChatView.tsx:468` (state hội thoại), `:486`, `:511` (processing), `:568` (answer_status), `:479` (user.role); `KnowledgeAdmin.tsx:46-47,52` (filter + cột); `TicketsView.tsx:128-139` (priority, escalate_reason); `HrKnowledgeApp.tsx:15`.

### P2 — Dev-speak / nội dung kỹ thuật lộ ra UI / mâu thuẫn terminology

| ID | Location | Current Content | Problem | Expected |
|----|----------|-----------------|---------|----------|
| C-06 | `HrKnowledgeApp.tsx:69` | Subtitle brand: "Kết nối Backend · Agent service riêng" | Kiến trúc nội bộ, vô nghĩa với user; làm sản phẩm nghe như công cụ dev. | Tagline sản phẩm: "Trợ lý AI tra cứu chính sách nội bộ" |
| C-07 | `HrKnowledgeApp.tsx:79,85-87` | DeferredView "CHƯA NỐI API" / "Giao diện đã sẵn sàng cho contract chính thức" / "Monitoring được giữ lại cho phase sau theo quyết định hiện tại" | Dev-speak; "contract" là từ kỹ thuật. Trang monitoring đúng là chưa có API (TASK-012 chưa làm) — cần lời trung thực, không jargon. | Eyebrow "ĐANG PHÁT TRIỂN" + mô tả trung thực không dùng dữ liệu mẫu |
| C-08 | `TicketsView.tsx:129` | "Chưa có ticket thật từ Backend." (QC UX-10) | Câu chữ hướng dev. | "Bạn chưa có yêu cầu hỗ trợ nào." |
| C-09 | `TicketsView.tsx:139` | "Lý do chuyển tiếp: `{escalate_reason}`" — enum thô | UX-03. | Map: `low_confidence`→"Độ tin cậy thấp", `out_of_scope`→"Ngoài phạm vi kho tài liệu", `personal_data_required`→"Cần dữ liệu cá nhân", `user_requested_human`→"Người dùng yêu cầu hỗ trợ" |
| C-10 | `ChatView.tsx:192-194` | "Backend chưa hỗ trợ API danh sách hội thoại." | Dev-speak; chỉ xảyra khi BE cũ. | "Chưa tải được danh sách hội thoại." |
| C-11 | `LoginView.tsx:87` | "Phiên đăng nhập dùng JWT do Backend phát hành." | Chi tiết implementation trên form user. | Ghi chú bảo mật hướng user hoặc bỏ |
| C-12 | `LoginView.tsx:35` + BE `auth_service.py:33` | Sai mật khẩu → "Invalid email or password" (EN) giữa UI VN (QC UX-02) | Mixed language. | FE map 401/UNAUTHORIZED → "Email hoặc mật khẩu không đúng." |
| C-13 | `AccessAdmin.tsx:50` | "Vai trò và phòng ban được lưu trong **ProfileDB**" | Tên bảng/DB nội bộ. | "…được lưu trong hồ sơ người dùng; mọi thay đổi được ghi lại để đối soát." |
| C-14 | `HrKnowledgeApp.tsx:15` | Nav "Ticket của tôi" cho cả admin, nhưng admin thấy hàng đợi ticket của mọi người | Label mâu thuẫn với nội dung trang theo persona. | Label động: employee "Ticket của tôi" / admin "Hàng đợi ticket" |
| C-15 | `KnowledgeAdmin.tsx:41-52` | Header bảng "Ingestion"/"Index"; filter option `ACTIVE/ARCHIVED` thô; pill `ingestion_state` thô | Kỹ thuật hóa ngôn ngữ quản lý kho. | "Xử lý"/"Chỉ mục" + label VN cho state/status (giữ nguyên giá trị gửi API) |

### P3 — Cosmetic (không sửa trong đợt này, trừ chi phí gần như 0)

| ID | Location | Current | Ghi chú |
|----|----------|---------|---------|
| C-16 | `TicketsView.tsx:126-128` | Priority "High/Medium/Low" EN | Sửa kèm C-05 vì đã có centralized labels (giá trị API giữ nguyên) |
| C-17 | `ChatView.tsx:528` | "Nguồn đã được xác thực nhưng chưa có đoạn trích" | "được xác thực" overclaim khi excerpt rỗng — làm mềm câu chữ kèm C-03 |
| C-18 | `TicketsView.tsx:135` | Category free-text default "GENERAL" | NEEDS PRODUCT DECISION — backend không có enum category; để nguyên |
| C-19 | `app/layout.tsx:8` | Meta description EN "…backed by verified company documents" + "verified" | Sửa kèm C-04 (việt hóa + bỏ "verified") |
| C-20 | `TicketsView.tsx:151` | TicketProgress hiện số 2/3/4 cho bước tương lai | Giữ nguyên (mô hình stepper phổ biến) |

### Nội dung đã đúng — giữ nguyên

- Citation trust row "Chính sách chính thức"/"Nguồn tham khảo" + label "Dữ liệu mô phỏng" cho
  `source_type=synthetic` (`ChatView.tsx:526,547-557`) — khớp yêu cầu `is_official_policy`
  trong ARCHITECTURE.
- Empty state chat + 2 câu gợi ý khớp corpus (WFH, ngày phép) — `ChatView.tsx:498-503`.
- Warning "Không đủ bằng chứng để trả lời một cách tin cậy." + "Liên hệ HR để được hỗ trợ."
  từ backend (`agent_answer_adapter.py:128-136`) — tiếng Việt, đúng behavior.
- FAILED retryable có nút "Thử lại" (`ChatView.tsx:576`) — khớp plan Phase 1 regression note.
- Ticket status labels tiếng Việt (`TicketsView.tsx:10-15`).

## C. CANONICAL TERMINOLOGY

| Concept | Canonical Term (FE) | Forbidden/Discouraged | Where Used |
|---|---|---|---|
| Trợ lý AI | "Trợ lý AI" / "Trợ lý AI HR" | "AI Model", "Bot", "Agent service" | Nav, login, chat |
| Kho tri thức | "Kho tài liệu" | "Dataset", "Training Data" | Admin nav, documents |
| Đối tượng tri thức | "Tài liệu" | "File" (khi nói knowledge object), "Document" EN | Documents, upload |
| Trích dẫn | "Nguồn đối soát" / "Trích dẫn" | "Citation" EN lộ ra UI | Chat panel |
| Từ chối trả lời | "Không đủ bằng chứng" | `REFUSED`, `INSUFFICIENT_EVIDENCE` thô | Answer pill, processing |
| Vai trò | "Nhân viên" / "Quản trị tri thức" / "Quản trị hệ thống" | Enum `HR_ADMIN`… thô trong UI user-facing | Sidebar, access admin |
| Xử lý tài liệu | "Xử lý (tài liệu)" / "Nhập liệu" | "Ingestion" thô | Documents table |
| Chỉ mục | "Chỉ mục" (giữ "index" trong ngoặc khi cần) | — | Documents, operations |
| Yêu cầu hỗ trợ | "Ticket" (giữ nguyên — đã là thuật ngữ chung) | — | Tickets |
| Hạ tầng | không nhắc tới trong UI user-facing | "Backend", "JWT", "API", "contract", "worker", "ProfileDB" | Mọi trang |

## D. FIX PLAN (Phase 2)

1. `lib/labels.ts` (mới): map tập trung state/status/role/reason/priority/scope/stage.
2. `KnowledgeAdmin.tsx`: thay panel khóa C-01 bằng Upload UI thật + poll job; wire C-02
   OperationsView (rebuild + evaluation + metrics); map label C-15.
3. `ChatView.tsx`: sửa note ticket C-03; map enum C-05; sửa C-10, C-17.
4. `HrKnowledgeApp.tsx`: C-06, C-07, C-14.
5. `LoginView.tsx`: C-04, C-11, C-12.
6. `TicketsView.tsx`: C-08, C-09, C-16.
7. `AccessAdmin.tsx`: C-13.
8. `app/layout.tsx`: C-19.

Không đổi business logic; mọi giá trị gửi lên API giữ nguyên enum gốc, chỉ đổi lớp hiển thị.

## E. FIXES APPLIED (Phase 2 — cùng ngày)

| Finding | File | Nội dung cũ | Nội dung mới |
|---|---|---|---|
| C-01 | `KnowledgeAdmin.tsx` | Panel "Upload tạm khóa — worker… chưa được triển khai" | Upload form thật (file + title/category/department/version/effective_date/access_scope) → `api.uploadDocument` → poll `getIngestionJob` theo `poll_after_ms`, hiển thị stage/progress/chunk_count, refresh danh sách khi COMPLETED |
| C-02 | `KnowledgeAdmin.tsx` | "Contract API đã có nhưng Backend chưa có worker thực thi" + 2 panel khóa | OperationsView thật: nút tái lập chỉ mục (`startIndexRebuild` + poll, progress + index version) và chạy đánh giá (`startEvaluation` với dataset từ `VALID_DATASETS` + poll + metric grid Recall@5/độ chính xác/phủ trích dẫn/P95) |
| C-03 | `ChatView.tsx` | "…có thể đã được Backend chuyển thành ticket theo kết quả Agent" | "Kho tài liệu hiện chưa đủ căn cứ… Hệ thống không tự tạo yêu cầu hỗ trợ — hãy tạo ticket ở mục Ticket để HR xử lý" |
| C-04 | `LoginView.tsx` | "Nguồn tin cậy — Chính sách được phê duyệt" | "Trả lời có trích dẫn — Kèm nguồn tài liệu để đối soát" |
| C-05 | `lib/labels.ts` (mới) + `ChatView/KnowledgeAdmin/TicketsView` | Enum thô (INSUFFICIENT_EVIDENCE, QUEUED, ACTIVE, HR_ADMIN, user_requested_human, High/Medium/Low…) | Bảng map tập trung + áp cho status pill, processing state, conversation state, role sidebar, ingestion/index/doc status, escalate_reason, priority |
| C-06 | `HrKnowledgeApp.tsx` | "Kết nối Backend · Agent service riêng" | "Trợ lý AI tra cứu chính sách nội bộ" |
| C-07 | `HrKnowledgeApp.tsx` | "CHƯA NỐI API" / "contract chính thức" / "Monitoring… phase sau" | "ĐANG PHÁT TRIỂN" + mô tả trung thực, không jargon, không dữ liệu mẫu |
| C-08 | `TicketsView.tsx` | "Chưa có ticket thật từ Backend." | Theo persona: "Bạn chưa có yêu cầu hỗ trợ nào." / "Chưa có yêu cầu hỗ trợ nào trong hàng đợi." |
| C-09 | `TicketsView.tsx` | escalate_reason thô | Map 5 lý do sang tiếng Việt |
| C-10 | `ChatView.tsx` | "Backend chưa hỗ trợ API danh sách hội thoại." | "Chưa tải được danh sách hội thoại." |
| C-11 | `LoginView.tsx` | "Phiên đăng nhập dùng JWT do Backend phát hành." | "Dùng email công ty đã đăng ký để truy cập kho chính sách nội bộ." |
| C-12 | `LoginView.tsx` | "Invalid email or password" (EN) | FE map 401→"Email hoặc mật khẩu không đúng.", 409→"Email này đã được đăng ký…" |
| C-13 | `AccessAdmin.tsx` | "lưu trong ProfileDB" | "lưu trong hồ sơ người dùng; mọi thay đổi được ghi lại để đối soát" |
| C-14 | `HrKnowledgeApp.tsx` | Nav "Ticket của tôi" cố định | Label động: employee "Ticket của tôi" / admin "Hàng đợi ticket" |
| C-15 | `KnowledgeAdmin.tsx` | Header "Ingestion"/"Index", option ACTIVE/ARCHIVED thô | "Xử lý"/"Chỉ mục", label tiếng Việt (giá trị API giữ nguyên) |
| C-16 | `TicketsView.tsx` | Priority EN | Cao/Trung bình/Thấp (giá trị gửi API giữ High/Medium/Low) |
| C-17 | `ChatView.tsx` | "Nguồn đã được xác thực…" | "Nguồn đã được ghi nhận…" |
| C-19 | `app/layout.tsx` | Meta description EN + "verified" | Tiếng Việt, khớp năng lực thật |

Regression: `pnpm typecheck` ✅ · `pnpm lint` (--max-warnings=0) ✅ · `pnpm build` ✅.

Còn mở (không sửa, có lý do): C-18 (ticket category free-text "GENERAL" — backend không có enum, NEEDS PRODUCT DECISION), C-20 (stepper số bước tương lai — giữ), monitoring API (TASK-012 backend — ngoài phạm vi FE audit).

---

## F. ADDENDUM — PRODUCT DECISION: "Tri thức nội bộ", KHÔNG phải chỉ HR (2026-08-23)

Product owner xác nhận: sản phẩm là **trợ lý tri thức nội bộ** (quy trình, quy định, biên bản,
quyết định, chính sách — đúng định vị Doc Intelligence Agent trong README), không thu hẹp
vào HR. Đợt audit đầu giữ branding "HR Knowledge" vì thiếu quyết định — nay đã có quyết định,
loại bỏ toàn bộ scope HR trong ngôn ngữ user-facing.

### Findings mới (từ quyết định định vị)

| ID | Location | Old | New |
|---|---|---|---|
| C-21 | `layout.tsx` | Title "HR Knowledge" | "Tri thức nội bộ" + description đúng phạm vi |
| C-22 | `HrKnowledgeApp.tsx` | Brand "HR Knowledge", nav "Trợ lý AI HR", nav "Index & RAG" (jargon) | Brand "Tri thức nội bộ", nav "Trợ lý AI", nav "Chỉ mục tìm kiếm" |
| C-23 | `LoginView.tsx` | "TRỢ LÝ AI HR DðA TRÊN BẰNG CHỨNG", h1 "Tri thức nhân sự…", "không gian HR Knowledge", "Tài khoản mới được Backend quản lý…" (dev-speak sót) | "TRỢ LÝ AI TRI THỨC NỘI BỘ", "Tri thức nội bộ…", "kho tri thức nội bộ", bỏ "Backend" |
| C-24 | `ChatView.tsx` | Empty state "chính sách nào", aria/placeholder "Câu hỏi HR", note REFUSED "để HR xử lý" | "thông tin nào" (quy trình/quy định/chính sách), "Câu hỏi", "người phụ trách xử lý" |
| C-25 | `TicketsView.tsx` | "HR SUPPORT", "Yêu cầu HR hỗ trợ", phòng tiếp nhận chỉ HRBP/CB/ER/TA/LD, "HR đã gửi kết quả", "kết quả của HR" | "YÊU CẦU HỖ TRỢ", "Gửi yêu cầu hỗ trợ", danh sách phòng ban chung (`DEPARTMENTS` chia sẻ với đăng ký), "Kết quả đã được gửi", ngữ thức trung tính |
| C-26 | `KnowledgeAdmin.tsx` | h2 "Tài liệu chính sách", placeholder "VD: leave_policies" | "Tài liệu nội bộ", "VD: company_regulations" |
| C-27 | Agent identity (`src/agents/nodes/router.py`) | Prompt chào hỏi tự giới thiệu "trợ lý HR nội bộ", mời hỏi "chính sách nhân sự"; template chào cố định同 | "trợ lý tri thức nội bộ", mời hỏi "quy trình, quy định và chính sách nội bộ" (chỉ đổi prompt text; intent enum/classification logic giữ nguyên) |
| C-28 | `src/agents/nodes/escalation.py` | Câu competitor: "chỉ hỗ trợ chính sách HR mẫu…", "liên hệ HR/C&B" | "chỉ chứa tài liệu nội bộ mẫu…", "bộ phận phụ trách" |
| C-29 | `backend/app/services/agent_answer_adapter.py` | Warning "Liên hệ HR để được hỗ trợ." | "Liên hệ người phụ trách để được hỗ trợ." |

Note: enum `hr_question` (intent), role `HR_ADMIN`, collection `hr_documents` là contract nội
bộ backend/agent — giữ nguyên, không đổi business logic. `src/evaluation/scoring.py` mô tả
"chatbot HR nội bộ" là prompt judge eval nội bộ (không user-facing) — để nguyên, NEEDS TEAM
REVIEW khi đổi bộ eval.

Canonical terminology cập nhật: **Sản phẩm = "Tri thức nội bộ"** (title/brand); KHÔNG dùng
"HR Knowledge", "Trợ lý AI HR", "chính sách nhân sự" như tên sản phẩm/phạm vi trong UI.
"HR" chỉ xuất hiện với ý nghĩa phòng ban HR (department option, corpus) — hợp lệ.

---

## G. ADDENDUM 2 — Role selector khi đăng ký + Font tiếng Việt (2026-08-23, theo yêu cầu product owner)

### G.1. Chọn vai trò ở form đăng ký (trong trang login)

Yêu cầu: "phần login phải thêm chỗ chọn role". Role là thuộc tính của **tài khoản** (lưu ở
`profiles.role`), không phải của phiên đăng nhập — nên selector đặt ở **tab Đăng ký**, không
phải tab Đăng nhập.

Ràng buộc bảo mật (phải giữ): DB trigger `prevent_self_privilege_escalation` (migration 0003)
+ test `test_api_register_cannot_self_assign_admin_role` chặn tự nâng quyền quản trị. Do đó:

- **BE** (`schemas/auth.py`, `services/auth_service.py`): `RegisterRequest` nhận thêm `role`;
  whitelist tự đăng ký = `{employee, department_user}` (2 vai trò không đặc quyền —
  `department_user` chỉ thêm quyền đọc tài liệu phạm vi phòng mình theo
  `config/access_policies.json`). Các role khác (hr_admin/super_admin/garbage) → 422
  `ROLE_NOT_ALLOWED_FOR_SIGNUP` kèm thông điệp tiếng Việt hướng dẫn đúng flow cấp quyền.
  Trigger migration 0003 vẫn là lớp chặn thứ hai.
- **FE** (`LoginView.tsx`, `lib/api.ts`): select "Vai trò" với 2 lựa chọn có mô tả nghĩa;
  form-note chỉ rõ vai trò quản trị do Quản trị hệ thống cấp qua trang Phân quyền.
- Test mới: `department_user` → 201; không gửi role → EMPLOYEE; `hr_admin` → 422 đúng code.

Ghi chú product: việc cho phép tự chọn `department_user` khi đăng ký tương đương với quyết
định Phase 6 (plan TASK-016) — product owner đã kích hoạt bằng yêu cầu này; runtime predicate
đã có test khóa riêng.

### G.2. Font tiếng Việt

Phát hiện gốc: **font chưa bao giờ được load** — không `<link>` Google Fonts, không
`next/font`; `styles.css` khai báo 'Work Sans' và `--serif` dùng "Instrument Serif" nhưng
không nơi nào tải chúng → toàn app render bằng fallback Arial/Georgia. Ngoài ra
"Instrument Serif" **không có subset vietnamese** nên kể cả khi load, dấu tiếng Việt ở
heading vẫn rơi về font khác.

Fix (`app/layout.tsx`, `next-app.css`, `styles.css`):
- Sans: **Be Vietnam Pro** (thiết kế riêng cho tiếng Việt, weight 400–800) qua
  `next/font/google`, subsets `["latin","vietnamese"]`, variable `--font-sans`, self-host
  khi build (đã verify woff2 trong `.next/static/media`).
- Serif heading: **Playfair Display** (có subset vietnamese, cùng phong cách display
  high-contrast thay Instrument Serif), variable `--font-serif`.
- CSS: `--sans`/`--serif` compose qua `var(--font-sans/--font-serif, fallback)`; universal
  selector `styles.css` bỏ 'Work Sans'.

### G.3. Regression đợt này

- FE: `pnpm typecheck` ✅ · `pnpm lint` ✅ · `pnpm build` ✅ (font self-host verified).
- Backend: 117 tests passed ✅ (3 test mới cho role signup); ruff sạch trên file đã sửa
  (kèm fix UP042 pre-existing `str, Enum` → `StrEnum`).

---

## H. ADDENDUM 3 — Kiểm toán & sửa phân quyền truy vấn theo phòng ban (2026-08-23 tối)

Câu hỏi product owner: "dữ liệu nhiều phòng ban, kiến thức không phải ai cũng query được,
phải có role đúng scope — hiện tại ai cũng truy vấn được toàn bộ dữ liệu à?"

### H.1. Hiện trạng đã xác minh (code + chạy thật)

Hệ thống CÓ sẵn ACL 2 lớp fail-closed, không phải "ai cũng query được hết":
1. **Registry corpus**: mỗi tài liệu có `access_scope` + `authorized_departments/roles`
   (`data/metadata/*_registry.csv`); `AuthorizationEngine.evaluate_access` check
   role→allowed_scopes (từ `config/access_policies.json`) + khớp phòng ban.
2. **Runtime uploads**: Chroma predicate fail-closed, sentinel `__NO_ACCESS__`.
3. Tenant isolation: collection theo tenant; `HR_ADMIN/SUPER_ADMIN` map → `ADMIN` (toàn quyền).

### H.2. Hai gap thật đã tìm thấy và sửa

| Gap | Bằng chứng | Fix |
|---|---|---|
| **42/73 docs gán sai COMPANY_WIDE**: toàn bộ corpus Accounting (10 docs — chứng từ DNTT/HDDT/PO/BBGN/QTCP) và Product (32 PRD) ai cũng query được dù là tài liệu nội bộ phòng | Quét 3 registry CSV: HR đúng (10 CW / 9 DEPT / 12 ROLE), Accounting + Product 100% COMPANY_WIDE | Sửa registry: cả 2 corpus → `DEPARTMENT` + authorized_departments; ACL layer-1 đọc CSV nên có hiệu lực ngay, không cần re-index |
| **Runtime predicate lỏng hơn policy**: EMPLOYEE đọc được DEPARTMENT runtime-upload cùng phòng dù `roles_policy` EMPLOYEE chỉ có COMPANY_WIDE | `authorization.py::runtime_upload_access_condition` cũ cấp grant DEPARTMENT/ROLE không check role; test cũ còn khóa hành vi lỏng này | Predicate giờ gate từng scope theo `roles_policy` (một nguồn sự thật); cập nhật test: DEPARTMENT cần DEPARTMENT_USER+, ROLE cần MANAGER+ |

Kèm theo: thêm phòng **Accounting** vào Department enum (đăng ký BE + DEPARTMENTS FE)
để user kế toán tự đăng ký đúng phòng; verify chạy thật:
EMPLOYEE(GENERAL) chỉ thấy 10 docs company-wide (0 PRD, 0 chứng từ);
DEPARTMENT_USER(Accounting) thấy chứng từ kế toán; DEPARTMENT_USER(Product) thấy PRD;
DEPARTMENT_USER(Finance) KHÔNG thấy chứng từ Accounting.

### H.3. Test

- `test_migration_parity` test_04/05 + **test_05b mới** (khóa scope 2 corpus): pass.
- `test_retrieval` (runtime predicate siết) + router/escalation/domains/guardrails: 120 pass.
- Backend 117 pass; FE typecheck/lint/build pass; ruff sạch file đã sửa (kèm fix
  F821 pre-existing: fallback policy dùng `false` JS thay `False` — bug NameError tiềm ẩn).

### H.4. Lưu ý môi trường trong phiên

`tests/test_agents/test_graph.py` (và parity 01-03) phụ thuộc Chroma Cloud/FPT thật
(comment trong test tự ghi "sẽ crash vì gọi FPT.AI/Chroma thật"). Tối 2026-08-23
Chroma Cloud degraded: cùng 1 test, code HEAD gốc cũng treo (đối chứng stash);
một lần chạy nền tự pass sau ~20 phút; filter ACL mới probe trực tiếp 0.3–0.5s.
→ Không phải regression của thay đổi; nên chạy lại suite khi cloud ổn định.

---

## I. ADDENDUM 4 — Security hardening: bịt các lỗ còn lại (2026-08-23 tối, theo yêu cầu product owner)

### I.1. Các lỗ đã sửa (kèm evidence trong code)

| ID | Lỗ | Trước | Sau |
|---|---|---|---|
| S-01 | **JWT secret mặc định đoán được** — `backend/app/core/config.py` fallback `"12345678900aaa"`: một lần deploy quên `.env` là forge được token admin | Không có check nào | `model_validator`: production + secret mặc định/short (<32 ký tự) → **từ chối khởi động**; thiếu `AI_AGENT_SERVICE_TOKEN` ở production → tương tự; dev/test in cảnh báo nhưng vẫn chạy |
| S-02 | **Agent API fail-open khi token trống** — `src/api/routes.py::_verify_service_token` dùng `if expected and ...`: không cấu hình `AGENT_SERVICE_TOKEN` là **bỏ qua hoàn toàn** kiểm tra | Bỏ qua check khi token trống (mọi môi trường) | Production + token trống → **401 từ chối mọi request**; dev/test giữ hành vi cũ để chạy local không cần .env (đồng bộ pattern với `verify_identity_signature` vốn đã fail-closed đúng) |
| S-03 | **Role lạ được cấp quyền đọc** — `evaluate_access` fallback cho role không có trong `roles_policy`: cấp COMPANY_WIDE + COMPANY_POLICY | Role lạ → đọc được tài liệu công ty | Role lạ → **từ chối hoàn toàn** (fail-closed, least-privilege). Lớp `UserContext.from_state` vốn đã chặn role lạ — đây là defense-in-depth |
| S-04 | **CI không có secret-scan** (TASK-014 trong Pilot plan) | Chỉ ruff + pytest | Thêm job `secret-scan` (gitleaks, scan full git history) vào `.github/workflows/ci.yml` |

### I.2. Test

- Mới: `backend/tests/test_config_security.py` (5 test khóa S-01); `test_05c` khóa S-03
  (parity); cập nhật `test_internal_agent_query_fails_closed_without_production_secret`
  khóa S-02 (401 thay 503 — signature layer không còn reachable khi token trống).
- Phát hiện & sửa luôn 4 test API pre-existing fail âm thầm trên máy có `.env`
  (thiếu `X-Identity-Signature` vì viết trước khi identity signature ra đời — CI xanh
  do không có .env nên check bị skip): `service_headers()` giờ ký HMAC identity đúng contract.
- Kết quả: `tests/test_api` 23 pass · parity ACL 4 pass · backend **122 pass** (117+5) ·
  ruff sạch mọi file đã sửa.

### I.3. HÀNH ĐỘNG MANUAL — chỉ product owner làm được (tôi không có quyền)

1. **Rotate 2 credential đã lộ trong terminal** (QC 22/08 phát hiện): Supabase DB
   password + Chroma Cloud API key — đổi trong console rồi cập nhật `.env`/`.env.example`
   của mọi máy thành viên.
2. Đẩy code lên remote để job `secret-scan` chạy lần đầu — nếu CI đỏ nghĩa là lịch sử
   git có secret thật (cần xử lý nghiêm túc, không tắt job).
3. Khi deploy production: đặt `APP_ENV=production` — các chặn S-01/S-02 tự kích hoạt.






---

## J. ADDENDUM 5 — Theo đề xuất production-readiness (2026-08-23 tối, đợt 2)

### J.1. Đồng bộ remote + push

Remote đã tiến 10 commit (team tự sửa determinism một phần, department-scoped retrieval
theo hướng khác, TASK-007 agent-side, registries DEPARTMENT sẵn). Đã rebase 4 commit của
phiên này lên origin/develop và **hòa giải ngữ nghĩa** thay vì text:

- `authorization.py`: giữ kiến trúc department-mandatory + `canonical_department` +
  `runtime_upload_metadata_allowed` của team; áp thêm policy-gating grants
  (`_role_policy_allows_scope`) và unknown-role deny của phiên này — hai nguồn sự thật
  (runtime predicate & registry ACL) nay cùng đọc `access_policies.json`.
- Policy mới của team: EMPLOYEE được thêm DEPARTMENT scope (quyết định Phase 6) —
  test `test_department_and_role_scopes_are_exact` cập nhật theo hành vi hợp nhất.
- KnowledgeAdmin upload UI: giữ bản phiên này (access_scope chọn được, fail-closed
  RESTRICTED mặc định, label tiếng Việt, accept đúng backend) + tích payload
  `confidentiality/status` và terminal CANCELLED của team.
- config validator: gộp cả hai bản (env-set + known-weak của team; ≥32 ký tự +
  agent-token bắt buộc + dev warning của phiên này).
- Đã push: `58c3462 → cddd0a6 → 8b58cfd` (6 commit).

### J.2. Các việc đã làm theo đề xuất

| Việc | Kết quả |
|---|---|
| Commit + push công sức phiên | 6 commit lên origin/develop; qa/ untrack (chứa token test) + gitignore |
| PR-01 TASK-004 | default `acall_llm` 0.5 → 0.0 (call site mới không thể vô tình sampling) |
| PR-02 TASK-007 | Agent/backend do team đã có; FE thêm render Mã tài liệu (document_code) |
| B4 rate limit | Sliding window 5 lần sai/5 phút theo (email, IP) → 429 + retry_after; 2 test mới |
| B4 password policy | min 8 ký tự BE + FE (kèm helper text — đóng UX-01) |
| B4 dependency audit | pip-audit (agent+backend) + pnpm audit FE trong CI (continue-on-error bước dọn nợ) |
| CI frontend job | Mới: lint + typecheck + build (trước đây CI không build FE) |

### J.3. Còn mở (chuyển tiếp)

- Rerank-down hiện `return []` (team chọn fail-closed vẫn REFUSED) — khác khuyến nghị
  FAILED-retryable của TASK-003; cần thống nhất trong team trước khi đổi (đã có test khóa).
- TASK-006 self-consistency marker borderline, TASK-008 grounding theo cited chunks:
  chưa làm (đụng sâu generation/escalation — làm riêng có baseline).
- CI lần đầu với secret-scan/frontend-build/pip-audit chưa quan sát được từ máy local
  (gh chưa auth) — cần xem trên GitHub Actions; nếu secret-scan đỏ thì lịch sử có
  secret thật, phải xử lý chứ không tắt job.
- Rotate 2 credential đã lộ: vẫn là hành động manual của product owner.
