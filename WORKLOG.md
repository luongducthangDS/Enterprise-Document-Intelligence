# Worklog — Team AI20K-Build-Phase-Cohort-3 (Project P-153)

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

---

## [2026-08-04]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Audit 3 file zip ở root, dọn trùng lặp, thêm `*.zip` vào `.gitignore` | ✅ Done | CLAUDE.md log | 0.5h |
| Lương Đức Thắng | Thiết kế cấu trúc thư mục data pipeline mới (`src/ingestion/`, `data/raw|processed|chunks|metadata|rejected`) + scaffold | ✅ Done | docs/folder_structure.md | 1h |
| Lương Đức Thắng | Đưa dữ liệu sẵn có (VinFast, Vingroup, bộ luật lao động...) vào cấu trúc mới, extract 5 PDF luật từ zip Google Drive | ✅ Done | data/raw/, document_registry.csv | 1h |
| Lương Đức Thắng | Tìm + verify + tải bổ sung văn bản pháp luật (Luật BHYT sửa đổi 51/2024, Luật TNCN hợp nhất, NĐ 161/2026 lương cơ sở, TT 60/2025/TT-BYT) — phát hiện và loại 1 file sai (NĐ 73/2024 đã hết hiệu lực) | ✅ Done | data/raw/government_legal/, data/rejected/ | 1.5h |
| Lương Đức Thắng | Xác định lại phạm vi dữ liệu (không gắn 1 công ty cụ thể — giải quyết pain point HR nói chung), tìm + verify + tải template công khai (nội quy lao động, quy chế lương thưởng, quy định nghỉ phép, quy trình chấm dứt HĐLĐ) | ✅ Done | data/raw/* — đủ 6/6 category | 1h |
| Lương Đức Thắng | Tìm config GLM-5.2 (qua FPT.AI Marketplace gateway) để chuẩn bị script tạo synthetic data (WFH policy, đào tạo & phát triển, FAQ eval set) | 🔄 WIP | Đã xác định base_url + model, đang chờ API key để lưu `.env` | - |

**Tổng kết ngày:** Hoàn thành khảo sát + tổ chức lại toàn bộ dữ liệu nguồn cho HR Document Intelligence Agent — pháp luật lao động/BHXH/BHYT/thuế TNCN, quy định nội bộ mẫu, và template công khai đều đã có trong `data/raw/` theo đúng 6 category. Còn thiếu: chạy extractor pipeline (`src/ingestion/`), sinh synthetic data cho 3 mảng chưa tìm được nguồn công khai đạt chất lượng, và xây eval set.

---

## [2026-08-05]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Dương | Dựng demo UI workflow đầu tiên cho luồng chat | ✅ Done | commit `1e8b3af` | - |
| Lương Đức Thắng | Data ingestion pipeline (extract/clean/chunk/embed/index) + schema Supabase + bộ eval dataset đầu tiên | ✅ Done | commit `a198c01` — `src/ingestion/`, `supabase/migrations/`, `eval/datasets/` | - |
| Lương Đức Thắng | Fix `setup_hooks.ps1` ghi BOM làm hỏng shebang của pre-push hook (AI usage logging) | ✅ Done | commit `8c6855b` | - |
| hthanhson | Thêm chức năng Sign in / Sign up | ✅ Done | commit `f4a4feb` | - |
| minhphu711 / minhphu | Dọn brief/PRD — bỏ bản markdown sinh tự động, giữ đúng 1 nguồn `.docx` | ✅ Done | commit `53861ab`, `cf05771`, PR #9 | - |

**Tổng kết ngày:** Ngày bận rộn nhất tuần — song song 4 mảng: UI demo, data ingestion pipeline hoàn chỉnh (data → chunk → embed → Chroma Cloud), auth (sign in/up), và dọn tài liệu PRD/brief. Đây là nền để dựng agent RAG ngày hôm sau.

---

## [2026-08-06]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Audit toàn bộ RAG pipeline + eval trước khi tối ưu (Phase 0) | ✅ Done | commit `cce1da2`, `docs/reports/project_review.md` | - |
| Lương Đức Thắng | Phát hiện + sửa 4 lỗi chết agent: reranker crash do `HF_HOME` trỏ ổ đĩa không tồn tại, `TypeError` khi thiếu `sentence-transformers`, escalate-theo-confidence bị vô hiệu hoá âm thầm, unit test gọi mạng | ✅ Done | reranker chuyển sang gọi qua FPT.AI gateway (`fpt_client.rerank()`) | - |
| Lương Đức Thắng | Sửa bộ eval: `ground_truth_context` dài hơn cả chunk (78/128 câu không thể khớp), qrel bị nới lỏng sai quy tắc, thiếu coverage 18/29 tài liệu | ✅ Done | commit `20b0250` — reranker/BM25/qrel eval infra + Phase 2 fixes | - |
| Lương Đức Thắng | Đo lại toàn bộ sau fix: in_scope pass 54/100 → 71/100, router accuracy 88.6% → 95.7%, cắt latency 22-23% (kết nối tái sử dụng, cache embedding, router model nhẹ hơn) | ✅ Done | commit `28d6231` | - |
| Lương Đức Thắng | Merge `origin/main` vào nhánh cá nhân (lịch sử không liên quan), sau đó bị revert bởi team | 🔄 WIP | commit `c65deac`, `db6975f`, revert `4490707` — cần thống nhất lại cách merge nhánh | - |
| hthanhson | Thêm Conversation API, Chat RAG API, Citation API cho backend | ✅ Done | commit `7b82468` | - |

**Tổng kết ngày:** Ngày nặng nhất về kỹ thuật — agent từ "không trả lời được câu nào" (reranker crash) đến pass rate 75.7%/140 câu cuối ngày. Phát hiện thêm rủi ro bảo mật đang sống (migration `0003`, RLS tự leo quyền `hr_admin`) và 2 backend song song (`src/api/` vs `backend/`) chưa chốt — ghi ở `docs/reports/ISSUES.md` (local, không lên GitHub). Sự cố merge/revert PR #10 cho thấy cần thống nhất lại quy tắc merge nhánh cá nhân với `main`.

---

## [2026-08-07]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Tách riêng tài liệu/report cá nhân (audit, review) khỏi repo GitHub — chỉ giữ local | ✅ Done | commit `86f9950` | - |
| Lương Đức Thắng | Gom lại script/docs ingestion + eval vào `scripts/rag_pipeline/`, `docs/rag-pipeline/` cho gọn cấu trúc | ✅ Done | commit `5653475` | - |
| Lương Đức Thắng | Merge `develop` mới nhất vào `feature/rag-agent-pipeline`, mở PR #11 | ✅ Done | commit `d61ca8a`, `72d4716` | - |
| Lương Đức Thắng | Rà soát dự án theo góc PM/BA, bổ sung các deliverable đang thiếu (README/ARCHITECTURE/JOURNAL/WORKLOG/architecture_diagram) | ✅ Done | file này + các file liên quan | - |

**Tổng kết ngày:** Dọn cấu trúc thư mục sau đợt sửa lỗi lớn hôm 08-06, merge nhánh RAG vào `develop`, và bù các deliverable bị bỏ trống từ đầu dự án (README vẫn là template, ARCHITECTURE/JOURNAL trống, architecture_diagram sai stack) — các mục này đang chấm 0 điểm dù công sức kỹ thuật đã đủ.

---

## [2026-08-19]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| minhphu | Sửa G5 retrieval miss cho `qa_013` và `qa_122` | ✅ Done | `0644efb`, `6ab84c5`; regression test pass | - |
| minhphu | Đồng bộ migration đủ schema backend, bỏ migration trùng số | ✅ Done | `32eb13f`, `b256cdb`; migration `0001`–`0007` | - |
| minhphu | Reconcile RLS trên Supabase thật và privilege guard | ✅ Done | `9fc83cb`; verify 10/10 bảng, RLS đầy đủ, trigger present | - |
| minhphu | Nối Backend ↔ Agent cho ingestion/index/evaluation lifecycle, bỏ metric evaluation mẫu | ✅ Done | `36419b9`; lifecycle test tới `COMPLETED` | - |
| minhphu | Làm sạch bộ test G6 và chạy regression toàn repo | ✅ Done | `4115e54`; core 421 pass, backend 106 pass | - |
| minhphu | Release agent held-out qua FPT.AI/Chroma Cloud | ✅ Done | Run hợp lệ 0/30; 0 lỗi hạ tầng; p50 10,0s, p95 59,7s | - |
| minhphu | Release retrieval held-out qua Chroma Cloud/FPT reranker | ✅ Done | 20 query; Hit@5 45%; Recall@5 29,6%; Doc Hit@5 15% | - |

**Tổng kết ngày:** Phần G5, migration/RLS và worker lifecycle đã hoàn tất bằng code + test + kiểm tra database thật. Hai release held-out đã chạy đúng một lần và ghi trung thực; quality gate không đạt, chủ yếu do retrieval/gold không khớp và contract legacy lệch phạm vi hiện tại.

---

## [2026-08-20]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Thiết kế mở rộng module retrieval cho domain Kế toán (`src/domains/accounting/retrieval_ext.py`) | ✅ Done | `src/domains/accounting/`, test suite | 2h |
| minhphu | Thu thập tài liệu quy định Kế toán và phân loại document registry cho Accounting | ✅ Done | `data/raw/accounting/`, `data/metadata/` | 2h |
| Dương | Khảo sát cập nhật giao diện Next.js hỗ trợ chọn phòng ban (`HR`, `Accounting`, `Product`) | ✅ Done | `frontend/components/` | 1.5h |
| hthanhson | Thiết kế mô hình phân quyền phòng ban tại backend API (`src/security/departments.py`) | ✅ Done | `src/security/` | 2h |

**Tổng kết ngày:** Bắt đầu mở rộng hệ thống từ chỉ chuyên biệt HR sang đa phòng ban (Multi-domain), tạo nền tảng cho domain Kế toán và Sản phẩm.

---

## [2026-08-21]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Xây dựng migration `0010_department_roles_and_company_scope.sql` và `0011_classify_existing_knowledge_documents.sql` | ✅ Done | `supabase/migrations/0010_*.sql`, `0011_*.sql` | 2.5h |
| hthanhson | Cập nhật `access_control.py` với logic fail-closed cho `COMPANY_WIDE` vs `DEPARTMENT_SPECIFIC` | ✅ Done | `backend/app/services/access_control.py` | 2h |
| Dương | Chuẩn hóa toàn bộ nhãn giao diện tiếng Việt và tối ưu font typography trên Next.js | ✅ Done | `frontend/lib/labels.ts`, `frontend/app/layout.tsx` | 1.5h |
| minhphu | Xây dựng kịch bản kiểm thử E2E Live 46 test cases không mock dependency | ✅ Done | `tests/e2e/live_harness.py`, `test_live_e2e.py` | 3h |

**Tổng kết ngày:** Hoàn thiện cơ chế phân quyền truy cập theo phòng ban (Department ACL) và chuẩn bị hạ tầng kiểm thử E2E Live trên môi trường thật.

---

## [2026-08-22]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Chạy 46 ca kiểm thử Live E2E, lập báo cáo `docs/E2E_TEST_REPORT.md` (36 PASS, 8 FAIL, 2 Critical) | ✅ Done | `docs/E2E_TEST_REPORT.md` | 3h |
| Lương Đức Thắng | Khắc phục triệt để BUG-01 (DTO mapping `pure_statutory`), BUG-02 (indexer collection SSOT resolver), BUG-03 (409 conflict) | ✅ Done | `docs/E2E_REMEDIATION_REPORT.md`, `src/ingestion/indexer.py` | 3.5h |
| minhphu / Dương | Kiểm thử UX Persona QC Report (`docs/UX_PERSONA_QC_REPORT_20260822.md`), bỏ animation quay vô hạn ở UI chat | ✅ Done | commit `08487c4`, `docs/UX_PERSONA_QC_REPORT_20260822.md` | 2h |
| hthanhson | Sửa phân quyền profile roles và cập nhật test fixtures post-merge | ✅ Done | commit `a82809a`, `backend/tests/` | 1.5h |

**Tổng kết ngày:** Ngày đột phá về chất lượng — chạy kiểm thử E2E thật và remediation dứt điểm các lỗi nghiêm trọng về collection naming và contract mapping giữa Backend và Agent.

---

## [2026-08-23]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| minhphu / Lương Đức Thắng | Thực hiện Product Content Audit 2026-08-23 (findings C-01 → C-29, addendum A-J) | ✅ Done | `docs/PRODUCT_CONTENT_AUDIT_20260823.md`, `PILOT_READINESS_IMPLEMENTATION_PLAN_20260823.md` | 3h |
| Lương Đức Thắng | Cập nhật định vị Agent thành 'Trợ lý Tri thức Nội bộ' (bỏ ràng buộc HR trong prompt greeting/clarify/refusal) | ✅ Done | commit `164affe`, `src/agents/nodes/` | 1.5h |
| hthanhson | Thắt chặt bảo mật phân quyền phòng ban fail-closed, scope corpus đúng phòng | ✅ Done | commit `6ac054e`, `backend/app/services/` | 2h |
| Dương | Cập nhật form đăng ký cho phép chọn phòng ban (`DepartmentSelect`) và kết nối API | ✅ Done | commit `4c960f4`, `frontend/components/LoginView.tsx` | 2h |

**Tổng kết ngày:** Hoàn thành định vị Trợ lý Tri thức Doanh nghiệp toàn diện, củng cố toàn bộ các tầng bảo mật ACL và kế hoạch sẵn sàng thử nghiệm (Pilot Readiness).

---

## [2026-08-24]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng | Thiết kế Schema & Migration `0012_document_review_workflow.sql` cho luồng HITL Document Review | ✅ Done | `supabase/migrations/0012_*.sql` | 2h |
| Lương Đức Thắng | Xây dựng Worker phân tích bóc tách cấu trúc tài liệu bằng LLM (`src/workers/document_analysis.py`) | ✅ Done | `src/workers/document_analysis.py`, Pydantic schemas | 3h |
| hthanhson | Xây dựng Endpoints API nạp và duyệt tài liệu (`/api/v1/document-submissions`) | ✅ Done | `backend/app/api/v1/endpoints/document_submissions.py`, service | 2.5h |

**Tổng kết ngày:** Đặt nền móng kỹ thuật cho tính năng Human-in-the-Loop (HITL) — bóc tách tự động Quyết định, Trách nhiệm, Deadline và hỗ trợ phê duyệt trước khi lưu vector database.

---

## [2026-08-25]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Dương | Xây dựng Component giao diện duyệt tài liệu HITL `DocumentReview.tsx` | ✅ Done | `frontend/components/DocumentReview.tsx` | 3.5h |
| hthanhson | Bổ sung Rate Limiting cho login và chính sách mật khẩu tối thiểu 8 ký tự | ✅ Done | commit `8b58cfd`, `backend/app/services/auth_service.py` | 2h |
| Lương Đức Thắng | Viết test suite kiểm thử quy trình phân tích tài liệu và API submissions | ✅ Done | `tests/test_workers/test_document_analysis.py`, `backend/tests/test_document_submissions.py` | 2h |

**Tổng kết ngày:** Hoàn tất trọn vẹn giao diện và backend cho tính năng Document Review HITL, đồng thời gia cố an ninh vận hành hệ thống.

---

## [2026-08-26]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Lương Đức Thắng / hthanhson | Viết file cấu hình Blueprint Render Cloud (`render.yaml`) và dịch vụ `warmup_service.py` | ✅ Done | `render.yaml`, `backend/app/services/warmup_service.py` | 2h |
| Dương | Tích hợp Component `WarmupPing.tsx` tự động giữ ấm container Backend & Agent trên cloud | ✅ Done | `frontend/components/WarmupPing.tsx` | 1h |
| Dương / hthanhson | Fix bug FE gọi sai service URL (`fbd0704`) và fix bug định tuyến ticket sai phòng ban (`09a9967`) | ✅ Done | `frontend/lib/api.ts`, `backend/app/services/ticket_service.py` | 1.5h |
| Lương Đức Thắng | Rà soát toàn bộ dự án, cập nhật và hoàn thiện 100% các file Markdown (`README.md`, `ARCHITECTURE.md`, `JOURNAL.md`, `WORKLOG.md`, `eval/`, `presentation/`) | ✅ Done | Trọn bộ 10 Deliverables | 2.5h |

**Tổng kết ngày:** Hệ thống hoàn toàn sẵn sàng cho Demo Day với đầy đủ tính năng Multi-domain, Document Review HITL, Phân quyền ACL, Blueprint Render Cloud, và toàn bộ 10 Deliverables hoàn chỉnh.
