# Hồ sơ dự án P-153

**Baseline đối chiếu:** `develop@87a85aa`  
**Ngày rà soát:** 2026-09-01

Thư mục này chứa cả tài liệu hiện hành và tài liệu nghiên cứu được tạo trong các giai đoạn trước. Khi có khác biệt, ưu tiên tài liệu chuẩn ở bảng dưới và mã nguồn/migration trên nhánh `develop`.

## Bộ tài liệu dùng cho bàn giao

| Hạng mục | Tài liệu chuẩn |
|---|---|
| Tổng quan và hướng dẫn chạy | [`../../README.md`](../../README.md) |
| Kiến trúc | [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) |
| Sơ đồ kiến trúc | [`../architecture_diagram.md`](../architecture_diagram.md) |
| Đặc tả và thiết kế | [`../SYSTEM_SPECIFICATION_AND_DESIGN.md`](../SYSTEM_SPECIFICATION_AND_DESIGN.md) |
| Kế hoạch/kết quả kiểm thử | [`../TESTING.md`](../TESTING.md) |
| Nhật ký tuần | [`../../JOURNAL.md`](../../JOURNAL.md) |
| Worklog theo commit `develop` | [`../../WORKLOG.md`](../../WORKLOG.md) |
| Checklist nộp bài | [`../FINAL_SUBMISSION.md`](../FINAL_SUBMISSION.md) |

## Tài liệu hiện hành trong `docs/project`

- [`integration/AGENT_BE_FE_INTEGRATION.md`](integration/AGENT_BE_FE_INTEGRATION.md): contract và luồng tích hợp FE–BE–Agent.
- [`database/relationDB.md`](database/relationDB.md): mô hình dữ liệu logic; migration trong `supabase/migrations/` vẫn là nguồn chuẩn vật lý.
- [`diagrams/`](diagrams/): các sơ đồ nguồn Mermaid tương thích với kiến trúc hiện tại.

## Tài liệu tham chiếu lịch sử

Các tệp sau ghi nhận quá trình phân tích/thiết kế trước đây, không dùng để khẳng định trạng thái triển khai hiện tại:

- `hr_interaction_boundary_plan.md`
- `hr_physical_schema_and_knowledge_spec.md`
- `PM_BA_Onboarding_Overview.md`
- `API/apiBackend.md`
- `API/APIdoc.md`
- `brief/Brief_HR_Document_Intelligence_Agent_Project.md`
- `prd/PRD_HR_Document_Intelligence_Agent.md`

Chúng được giữ lại để truy vết quyết định. Endpoint, role, metric và trạng thái tính năng trong các tệp này có thể đã thay đổi.

## Demo và kiểm thử thủ công

- `demo/demoMVP.mp4` là video demo lịch sử, không thay cho test report tại baseline hiện tại.
- `test-cases/MLC_ERP_Final_Product_Manual_Test_Cases.xlsx` có 7 case (6 PASS, 1 FAIL). Khi rà soát ngày 2026-09-01, cả 32 ô evidence trong các sheet chi tiết hiển thị `#VALUE!`; vì vậy workbook chưa đủ bằng chứng để kết luận nghiệm thu. Không được đổi TC04 sang PASS hoặc điền evidence nếu chưa chạy lại và đính kèm ảnh/log thật.

## Quy ước cập nhật

1. Ghi baseline commit và ngày chạy test cho mọi kết quả định lượng.
2. Không mô tả tính năng dự kiến như tính năng đã triển khai.
3. Role chuẩn là `EMPLOYEE`, `DEPARTMENT_MANAGER`, `SUPER_ADMIN`.
4. Frontend gọi Backend; Backend mới được gọi Agent bằng service token và signed identity.
5. Khi schema tài liệu khác migration, ưu tiên migration và cập nhật lại tài liệu trong cùng pull request.
