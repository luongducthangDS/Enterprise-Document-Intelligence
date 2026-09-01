# Danh mục bàn giao cuối — P-153

**Baseline source:** `develop@87a85aa`
**Ngày lập hồ sơ:** 2026-09-01

Thư mục đóng gói dành cho mentor: [`docs-final/`](docs-final/).

## 1. Source code

- Agent/RAG/ingestion/workers: [`../src/`](../src/)
- Backend API: [`../backend/`](../backend/)
- Frontend: [`../frontend/`](../frontend/)
- Database migrations: [`../supabase/migrations/`](../supabase/migrations/)
- Automated tests: [`../tests/`](../tests/) và [`../backend/tests/`](../backend/tests/)
- Evaluation: [`../eval/`](../eval/)
- Deployment: [`../docker-compose.yml`](../docker-compose.yml), [`../render.yaml`](../render.yaml)

## 2. README

- [`../README.md`](../README.md)

README chứa phạm vi, năng lực thực tế, quick start, cấu hình, cấu trúc repository, testing entry point và mapping thành viên/Git author.

## 3. Architecture diagram

- Tài liệu kiến trúc: [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- Bộ sơ đồ Mermaid chuẩn: [`architecture_diagram.md`](architecture_diagram.md)
- Diagram sources bổ sung: [`project/diagrams/`](project/diagrams/)

## 4. Đặc tả và thiết kế

- Tài liệu chuẩn: [`SYSTEM_SPECIFICATION_AND_DESIGN.md`](SYSTEM_SPECIFICATION_AND_DESIGN.md)
- Mục lục và phân loại tài liệu dự án: [`project/README.md`](project/README.md)
- PRD/brief lịch sử: [`project/prd/`](project/prd/), [`project/brief/`](project/brief/)
- API/integration/database references: [`project/API/`](project/API/), [`project/integration/`](project/integration/), [`project/database/`](project/database/)

## 5. Tài liệu kiểm thử

- Strategy, commands, latest verification và known issues: [`TESTING.md`](TESTING.md)
- E2E matrix: [`E2E_TEST_MATRIX.md`](docs-final/references/E2E_TEST_MATRIX.md)
- Historical live report/remediation: [`E2E_TEST_REPORT.md`](docs-final/references/E2E_TEST_REPORT.md), [`E2E_REMEDIATION_REPORT.md`](docs-final/references/E2E_REMEDIATION_REPORT.md)
- Eval datasets/results: [`../eval/datasets/`](../eval/datasets/), [`../eval/results/`](../eval/results/)
- Final metrics report: [`../eval/results/report.md`](../eval/results/report.md)
- Manual workbook: [`project/test-cases/MLC_ERP_Final_Product_Manual_Test_Cases.xlsx`](project/test-cases/MLC_ERP_Final_Product_Manual_Test_Cases.xlsx) — hiện có 1 FAIL và evidence lỗi; xem cảnh báo trong `TESTING.md`.

## 6. Weekly logs

- Weekly journal: [`../JOURNAL.md`](../JOURNAL.md)
- Commit-backed daily/weekly worklog: [`../WORKLOG.md`](../WORKLOG.md)

## Tình trạng kiểm chứng

| Hạng mục | Trạng thái hồ sơ |
|---|---|
| Source code | Có trong repository; còn quality-gate issues được liệt kê trong `TESTING.md` |
| README | Đã đồng bộ baseline 31/08 |
| Architecture | Đã đồng bộ source hiện tại |
| Specification/design | Đã có tài liệu chuẩn và traceability tới code |
| Testing | Đã ghi kết quả thật, phân biệt live/offline/environment-blocked |
| Weekly logs | Đã dựng từ lịch sử commit `develop` |

File này là mục lục bàn giao, không phải chứng nhận mọi quality gate đã pass.
