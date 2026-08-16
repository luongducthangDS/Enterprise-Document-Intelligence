# Worklog — Team [Tên Team]

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| [Tên] | [mô tả task] | ✅ Done | [link/kết quả] | 2h |
| [Tên] | [mô tả task] | 🔄 WIP | [mô tả tiến độ] | 1.5h |
| [Tên] | [mô tả task] | ❌ Blocked | [lý do block] | - |

**Tổng kết ngày:** [1-2 câu về tiến độ chung]

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

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
