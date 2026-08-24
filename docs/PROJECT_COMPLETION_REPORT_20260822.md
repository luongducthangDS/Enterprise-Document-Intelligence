# Báo cáo hoàn thành hệ thống RAG và phân quyền

**Ngày:** 2026-08-22  
**Nhánh:** `develop`  
**Commit:** `3dda777`  
**Remote:** `origin/develop`

## Tóm tắt

MVP cốt lõi của hệ thống RAG đa phòng ban đã hoàn thành: xử lý dữ liệu, embedding, Chroma Cloud, domain routing, eval/guardrail, xác thực và ACL tài liệu.

| Domain | Collection | Chunks |
|---|---|---:|
| HR / Nhân sự | `tenant_nexatech_knowledge` | 269 |
| Accounting / Kế toán | `accounting_documents` | 152 |
| Product / Sản phẩm | `product_documents` | 82 |

## Đã hoàn thành

### Data và retrieval

- Extract, làm sạch, chunking và embedding dữ liệu.
- Index vector/metadata lên Chroma Cloud.
- Tách collection Accounting/Product khỏi collection HR.
- Tenant được đưa vào chunk ID, metadata và collection routing.
- Domain routing, dense retrieval, hybrid BM25 và reranking.
- Accounting có query expansion, dynamic top-k, OCR handling và hard-block chống lách quy trình.
- Product nhận diện được cả các câu hỏi tiếng Việt chung như “tính năng”, “phát hành”, “thử nghiệm”.

### Eval và guardrail

- Có retrieval eval, held-out set, qrels và citation checks cho ba domain.
- Có guardrail datasets và kết quả chạy qua FPT Cloud.
- Có hallucination check, confidence, escalation và xử lý câu hỏi nhạy cảm.
- Đã sửa regression để câu hỏi HR về bảo hiểm/người phụ thuộc không bị nhận nhầm là Accounting.

### Backend, frontend và Docker

- Backend FastAPI, async chat polling, citation và ticket flow.
- Frontend chat và màn hình quản trị truy cập.
- Agent service nội bộ có service token.
- Docker Compose đã rebuild/recreate; Backend, Agent và Frontend đều healthy.

### Database và migration

- Đã áp dụng `0006_document_authority_provenance.sql`.
- Đã áp dụng `0008_document_runtime_acl.sql`.
- Đã áp dụng `0009_access_admin_audit.sql`.
- Đã xác nhận cột ACL trên `documents`, bảng `audit_logs`, RLS và trigger chống tự nâng quyền.

## Phân quyền MVP

Danh tính được lấy từ database và reload khi request:

- `user_id`
- `tenant_id`
- `department`
- `role`
- `permissions`

Phạm vi tài liệu:

| Scope | Quyền |
|---|---|
| `COMPANY_WIDE` | Mọi phòng trong tenant |
| `DEPARTMENT` | Chỉ phòng được chỉ định |
| `ROLE` | Chỉ role được chỉ định |
| `RESTRICTED` | Owner/người được cấp trực tiếp |

Ví dụ:

- Nhân viên Product xem tài liệu Product và tài liệu công ty dùng chung.
- Nhân viên Product không xem tài liệu HR chỉ dành cho HR như tuyển dụng, onboarding, offboarding.
- Tài liệu HR `COMPANY_WIDE` vẫn được Product xem; đây là hành vi đúng theo policy hiện tại.
- Role cao hơn chỉ có thêm quyền khi policy cấp, không tự động xem tất cả.
- Admin quản trị user/role/phòng ban/ACL; thay đổi được ghi vào `audit_logs`.
- Tenant khác nhau được tách biệt.

Role nghiệp vụ chính: `EMPLOYEE`, `MANAGER`, `DEPARTMENT_USER`, `HR_OPERATOR`, `LEGAL_COUNSEL`, `FINANCE_OFFICER`, `EXECUTIVE`, `ADMIN`.

Role quản trị catalog: `HR_ADMIN`, `SUPER_ADMIN`; hai role này được ánh xạ thành quyền admin khi gửi context sang Agent.

## Kiểm thử

- Root suite trước merge: 521 passed.
- Backend suite trước merge: 110 passed.
- Frontend build: passed.
- Regression routing/retrieval/graph sau merge Accounting: 79 passed.
- Domain routing Product sau sửa: 14 passed.
- Docker health smoke test: passed.
- Production log xác nhận Product request dùng `collection=product_documents`.

## Chưa hoàn thành/chưa xác nhận

- Chưa xác nhận deploy commit mới nhất lên máy chủ production bên ngoài Docker hiện tại.
- Docker hiện báo `APP_ENV=development`; cần cấu hình `APP_ENV=production` khi triển khai thật.
- Chưa có staging E2E chính thức với tài khoản thật của HR, Accounting, Product và manager.
- Chưa chạy đầy đủ ma trận ACL production: đúng phòng, sai phòng, cross-department, role và restricted owner.
- Structured knowledge extraction chưa nối hoàn chỉnh vào ingestion runtime/Agent.
- Cross-document knowledge graph/lineage mới ở mức nền tảng.
- Human-in-the-loop approval, monitoring/alerting production và audit dashboard nâng cao chưa hoàn thiện.
- Chưa chạy lại toàn bộ answer-level eval sau deployment production cuối cùng.

## Khuyến nghị tiếp theo

1. Deploy commit `3dda777` lên staging với `APP_ENV=production`.
2. Chuẩn bị tài khoản test cho HR, Accounting, Product và role quản lý.
3. Chạy ma trận E2E phân quyền, lưu request ID và citations.
4. Chạy lại answer-level eval/guardrail sau deploy.
5. Hoàn thiện structured knowledge và human approval sau khi MVP ổn định.

## Lưu ý vận hành

- Không chạy `docker compose down -v` nếu cần giữ dữ liệu.
- Migration phải được chạy trước khi bật runtime ACL trên môi trường mới.
- Không chia sẻ JWT, API key, database password hoặc nội dung tài liệu nhạy cảm trong log.
