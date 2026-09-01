# Hồ sơ tài liệu cuối P-153

**Baseline:** `develop@87a85aa`

**Ngày rà soát:** 2026-09-01

Thư mục này gom các tài liệu chính dùng để mentor review. Bản trong thư mục là snapshot bàn giao; source canonical vẫn được duy trì tại vị trí gốc trong repository.

| STT | Tài liệu | File |
|---:|---|---|
| 1 | Sơ đồ kiến trúc | [`01_ARCHITECTURE_DIAGRAM.md`](01_ARCHITECTURE_DIAGRAM.md) |
| 2 | Đặc tả và thiết kế | [`02_SYSTEM_SPECIFICATION_AND_DESIGN.md`](02_SYSTEM_SPECIFICATION_AND_DESIGN.md) |
| 3 | Tài liệu kiểm thử | [`03_TESTING.md`](03_TESTING.md) |
| 4 | Metrics & Evaluation toàn hệ thống | [`04_EVAL_METRICS.md`](04_EVAL_METRICS.md) |

## Diagram sources

Thư mục [`diagrams/`](diagrams/) chứa sáu Mermaid sources và `viewer.html`, đã đối chiếu với code hiện tại:

- System overview
- Component diagram
- Data flow
- Agent flow
- Deployment
- User/system workflow

Thư mục [`references/`](references/) giữ API/worker contracts và các E2E reports được tài liệu chính tham chiếu, để bộ bàn giao không phụ thuộc vào các tài liệu lịch sử đang được sắp xếp lại ở ngoài thư mục này.

Để dùng viewer, chạy HTTP server tại repository root rồi mở `docs/docs-final/diagrams/viewer.html`; không mở trực tiếp bằng `file://` vì trình duyệt sẽ chặn `fetch()` các Mermaid source.

## Trạng thái chất lượng

Tài liệu phản ánh đúng cả phần đã pass và phần còn bị chặn/chưa đạt. `04_EVAL_METRICS.md` kết luận hệ thống ở mức `CONDITIONALLY READY`, không phải chứng nhận mọi quality gate đã pass.
