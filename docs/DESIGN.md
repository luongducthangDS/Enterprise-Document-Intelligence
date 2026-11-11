# Design

UI theo vai trò: đặc tả mục 10. Token ở `frontend/styles.css`.

## Màu
- Nền app `--bg-app #F8FAFC`, bề mặt `#FFFFFF`, sidebar navy `--bg-sidebar #0F172A` (hover `#1E293B`).
- Viền `--border-subtle #E2E8F0`, `--border-strong #CBD5E1`.
- Chính: navy `#0F172A`, xanh `--primary-blue #2563EB` (hover `#1D4ED8`, nền nhạt `#EFF6FF`).
- Trạng thái: đã xác minh emerald `#059669` / nền `#ECFDF5`; cảnh báo amber `#D97706` / `#FFFBEB`; nguy hiểm rose `#E11D48` / `#FFF1F2`.
- Chữ: `--text-main #0F172A`, `--text-body #334155`, `--text-muted #64748B`, `--text-light #94A3B8`.

## Hình khối và chữ
- Bo góc 4 / 6 / 8 / 12 px; 3 mức đổ bóng; chuyển động `0.15s ease`.
- Font `Be Vietnam Pro` → Segoe UI → Arial; mã dùng `JetBrains Mono`; khung xem DOCX dùng Calibri.
- Chế độ sáng. (unverified: không thấy dark mode)

## Thành phần đáng chú ý
Thẻ trích dẫn mở và highlight DOCX/PDF, dòng `status` tiến trình tool qua SSE, `TicketProposalCard` để xác nhận tạo case.
