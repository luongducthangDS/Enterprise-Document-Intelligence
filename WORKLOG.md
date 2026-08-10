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

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
