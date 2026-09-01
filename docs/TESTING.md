# Tài liệu kiểm thử P-153

**Baseline:** `develop@87a85aa`
**Lần kiểm chứng cục bộ gần nhất:** 2026-09-01
**Mục đích:** Mô tả chiến lược, phạm vi, cách chạy và kết quả có thể tái lập; không thay thế kết quả live bằng suy đoán.

## 1. Chiến lược kiểm thử

| Tầng | Mục tiêu | Vị trí |
|---|---|---|
| Unit | Router, graph, guardrail, chunker, retrieval utilities, schemas | `tests/test_agents`, `tests/test_ingestion`, `tests/test_retrieval` |
| Service/API | Auth, chat, conversation, citation, document, ticket, review, warmup | `backend/tests` |
| Security | Tenant isolation, department ACL, identity signature, prompt injection, PII | `tests/test_security_*`, `tests/test_safety_guardrails.py`, backend access tests |
| Worker | Analysis, ingestion, indexing, evaluation, job lifecycle | `tests/test_workers`, backend worker tests |
| Contract/integration | Backend–Agent DTO, streaming, polling/recovery, migration manifest | `tests/test_api`, `tests/test_migrations`, backend integration tests |
| Live E2E | Real Backend + Agent + PostgreSQL + Chroma + model provider | `tests/e2e`, `docs/E2E_TEST_MATRIX.md` |
| RAG evaluation | Router/retrieval/agent/guardrail metrics và held-out datasets | `eval/scripts`, `eval/datasets`, `eval/results` |
| Static quality | Python lint, TypeScript, ESLint, frontend build | Ruff, `pnpm lint/typecheck/build`, GitHub Actions |

## 2. Ma trận năng lực cần kiểm tra

| Nhóm | Kịch bản tối thiểu | Kết quả mong đợi |
|---|---|---|
| Auth/RBAC | Register, login, refresh, self-escalation, last-admin | Token hợp lệ; role bị giới hạn; thao tác đặc quyền bị chặn |
| Chat | New/existing conversation, SSE, polling fallback, retry | State bền vững; final answer không bị ghi đè sai |
| Routing | Greeting, capability, ambiguous, knowledge, personal, pure statutory | Đi đúng graph branch và runtime state |
| Retrieval | HR/Accounting/Product, temporal query, multi-source | Chunks đúng domain, đa nguồn khi cần |
| ACL | Cross-department, unknown role, tenant mismatch | Không chunk trái quyền lọt vào context |
| Grounding | Citation marker, numeric claim, no evidence | Trả có nguồn hoặc abstain/escalate |
| Documents | PDF/DOCX/XLSX/MD/image, large file, duplicate | Extract hoặc lỗi nghiệp vụ rõ ràng; không 500 mơ hồ |
| HITL | Submit → analyze → review → approve/reject | Chỉ approved version được index |
| Versioning | Publish v2, rename source, archive | Version cũ không còn eligible trong retrieval |
| Citation viewer | Page/sheet/section/version, resize PDF | Mở đúng nguồn và highlight đúng vùng |
| Ticket | Own/department/admin access, closure audit | Đúng owner/department và có audit |
| Recovery | Backend/Agent restart giữa job/chat | Không kẹt trạng thái vô hạn |

Chi tiết Given/When/Then của bộ live: [`E2E_TEST_MATRIX.md`](docs-final/references/E2E_TEST_MATRIX.md).

## 3. Môi trường và dependency

### Offline/local

- Python dependencies từ `requirements.txt` và `backend/requirements.txt`.
- Frontend dependencies từ `frontend/pnpm-lock.yaml`.
- Unit tests phải mock network hoặc dùng local fixtures.

### Live/integration

- PostgreSQL/Supabase schema đã apply migration.
- Chroma Cloud/local chứa đúng collections và metadata baseline.
- Model provider/embedding/rerank credentials hợp lệ.
- `ACTIVE_TENANT`, department registry và collection resolver đồng nhất.

Không chạy test live rồi diễn giải lỗi network là lỗi chất lượng model. Ngược lại, test được đặt trong suite mặc định nhưng bắt buộc gọi cloud cần được đánh dấu rõ hoặc tách marker để CI sạch có thể tái lập.

## 4. Lệnh chạy chuẩn

```bash
# Agent/core
pytest tests -q
ruff check src tests

# Backend
cd backend
pytest tests -q
ruff check app tests

# Frontend
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build

# Dataset integrity
python eval/scripts/check_dataset_integrity.py

# Live E2E — chỉ chạy khi đã cấu hình môi trường thật
pytest tests/e2e -v
```

Held-out datasets không được chạy lặp lại để tune rồi báo như kết quả release độc lập.

## 5. Kết quả kiểm chứng 2026-09-01

### Backend Pytest

Lệnh: `python -m pytest tests -q` trong `backend/`.

| Kết quả | Giá trị |
|---|---:|
| Passed | 152 |
| Failed/Error | 0 |
| Warnings | 10 |

Các warning đáng chú ý: Starlette deprecation và thread `aiosqlite` cố trả kết quả sau khi event loop test đã đóng. Test pass nhưng warning lifecycle nên được xử lý trước khi đặt quality gate “không warning”.

### Agent/core Pytest

Lệnh: `python -m pytest tests -q` tại root.

| Kết quả | Giá trị |
|---|---:|
| Passed | 589 |
| Skipped | 44 |
| Failed | 6 |
| Errors | 8 |
| Subtests passed | 6 |

Phân loại:

- 8 errors trong `test_migration_parity.py`: setup kết nối Chroma thất bại trong môi trường bị chặn mạng.
- 4 failures trong `test_production_cutover_smoke.py`: retrieval cần FPT/Chroma live nhưng không kết nối được.
- 2 failures trong `test_agents/test_llm_config.py`: cấu hình provider/credential từ môi trường ảnh hưởng kỳ vọng unit test; đây là vấn đề isolation/configuration cần xử lý, không được gộp vào lỗi network.

### Ruff

| Phạm vi | Kết quả |
|---|---:|
| `ruff check src tests` | 150 findings |
| `ruff check app tests` trong Backend | 78 findings |

Phần lớn là import order, unused import, whitespace và modernization; vẫn có các finding cần xem thủ công như undefined name hoặc import không ở đầu module. Vì vậy tuyên bố cũ “Ruff sạch” đã bị loại khỏi README.

### Frontend

Đã cài dependency theo lockfile và chạy lại trên baseline hiện tại:

| Gate | Kết quả |
|---|---:|
| `pnpm lint` | PASS |
| `pnpm typecheck` | PASS |
| `npm run build` | PASS (Next.js 15.5.23; compile 21.0s) |
| `pnpm audit --audit-level high` | FAIL: 3 High, 2 Moderate |

Frontend compile và kiểm tra kiểu thành công, nhưng dependency-security gate chưa đạt do advisory qua `sharp` và `postcss`.

### Workbook kiểm thử thủ công

Tệp: [`project/test-cases/MLC_ERP_Final_Product_Manual_Test_Cases.xlsx`](project/test-cases/MLC_ERP_Final_Product_Manual_Test_Cases.xlsx).

| Chỉ số | Giá trị |
|---|---:|
| Test cases | 7 |
| PASS | 6 |
| FAIL | 1 (`TC04`) |
| Evidence cells lỗi | 32 (`#VALUE!`) |

Đã render và kiểm tra đủ 8 sheet ngày 2026-09-01. Bố cục đọc được, nhưng toàn bộ cột evidence của các sheet chi tiết đang chứa giá trị lỗi và không có công thức hợp lệ để truy vết. Vì vậy workbook được xem là **manual test record chưa hoàn chỉnh**, không phải bằng chứng release acceptance. Cần chạy lại TC01–TC07, sửa TC04 hoặc ghi nhận accepted defect, rồi đính kèm screenshot/log thật trước khi nộp.

## 6. Evaluation report cuối

- [`../eval/results/report.md`](../eval/results/report.md): báo cáo metrics canonical cho mentor tại baseline `develop@87a85aa`.
- [`../eval/results/final_system_evaluation_20260901.json`](../eval/results/final_system_evaluation_20260901.json): artifact tổng hợp toàn hệ thống.
- [`../eval/results/final_offline_eval_20260901.json`](../eval/results/final_offline_eval_20260901.json): raw artifact chạy lại, không gọi network.
- [`../eval/results/final_boundary_20260901.json`](../eval/results/final_boundary_20260901.json): chi tiết 68 boundary cases.

## 7. Kết quả lịch sử

Các artifact sau có giá trị theo đúng timestamp và baseline của chúng:

- [`E2E_TEST_REPORT.md`](docs-final/references/E2E_TEST_REPORT.md): phiên live acceptance ngày 2026-08-22.
- [`E2E_REMEDIATION_REPORT.md`](docs-final/references/E2E_REMEDIATION_REPORT.md): sửa BUG-01 đến BUG-07 tại baseline tương ứng.
- `eval/results/*.json`: raw metrics và run artifacts.

Không suy rộng kết quả 22–26/08 cho code 31/08 nếu chưa chạy regression trên baseline mới.

## 8. Quality gate đề xuất cho bản nộp

| Gate | Điều kiện đạt |
|---|---|
| Backend | Pytest pass; không có warning lifecycle nghiêm trọng |
| Agent offline | Tất cả unit/integration offline pass; test cloud được marker hóa |
| Live RAG | Chạy đúng tenant/index/model config; lưu raw report và timestamp |
| Security | Tenant/department/unknown-role/prompt-injection/PII suites pass |
| Frontend | Install lockfile, lint, typecheck và build pass |
| Static Python | Ruff không còn error; có thể giữ warning được phê duyệt nếu cấu hình rule rõ |
| Documentation | README/architecture/spec/testing/worklog links tồn tại và không claim sai baseline |

## 9. Known issues cần theo dõi

| ID | Vấn đề | Mức ảnh hưởng |
|---|---|---|
| QA-01 | Unit test LLM config bị ảnh hưởng bởi environment credential/provider | Làm test không hermetic |
| QA-02 | Live Chroma/FPT tests nằm trong root suite mặc định | CI/local sạch có thể fail vì network |
| QA-03 | Ruff còn findings | Chất lượng tĩnh chưa đạt gate |
| QA-04 | Backend test có `aiosqlite` closed-loop warnings | Có thể che lỗi cleanup resource |
| QA-05 | Frontend audit còn 3 High và 2 Moderate vulnerabilities | Dependency-security gate chưa đạt |
| QA-06 | Monitoring UI là placeholder | Không tính là acceptance-complete |
| QA-07 | Workbook manual test có 32 ô evidence `#VALUE!` và TC04 FAIL | Chưa đủ bằng chứng nghiệm thu thủ công |
| QA-08 | `document_submissions.file_content` nullable trong ORM nhưng `NOT NULL` ở migration `0012` | Luồng `/document-submissions/from-url` có thể pass SQLite test nhưng fail trên Supabase tạo từ migration |

## 10. Quy tắc báo cáo

- Ghi commit SHA, ngày, command và môi trường cho mỗi kết quả.
- Tách rõ Passed, Failed, Skipped, Not Run và Environment Blocked.
- Không dùng tỷ lệ 100% khi mẫu chỉ là một subset hoặc baseline cũ.
- Không đưa secret, token hoặc thông tin tài khoản test vào log/artifact.
