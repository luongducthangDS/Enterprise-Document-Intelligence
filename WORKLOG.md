# Worklog — Team [Tên Team]

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

**Tổng kết ngày:** Phần G5, migration/RLS và worker lifecycle đã hoàn tất bằng code + test + kiểm tra database thật. Agent held-out đã chạy đúng một lần và ghi trung thực 0/30; retrieval held-out 20 query còn chờ quyền data egress riêng.

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
