# P-153 — ĐỐI CHIẾU PROJECT STATUS REPORT VỚI HỆ THỐNG HIỆN TẠI

**Ngày đối chiếu:** 2026-08-22  
**Báo cáo nguồn:** `C:\Users\Admin\Downloads\PROJECT_STATUS_REPORT.md`  
**Phạm vi xác minh:** workspace `D:\P-153`, Chroma Cloud read-only, FPT Cloud eval/guardrail  
**Lưu ý triển khai:** kết quả dưới đây phản ánh code và test trong workspace hiện tại. Các migration mới chưa được xác nhận đã apply lên Supabase production và worktree chưa commit/deploy.

## 1. Kết luận điều hành

P0 data/RAG và nền quản trị phân quyền đã hoàn tất trong workspace:

- Ba domain HR/Core, Accounting và Product có collection riêng, routing riêng, không fallback chéo domain.
- Write path đã tenant-safe từ artifact filesystem, chunk ID, collection routing đến delete/rebuild.
- Runtime upload có ACL và lifecycle fail-closed xuyên suốt Backend → worker → Chroma metadata.
- Identity Backend → Agent được ký HMAC; Agent không còn identity default; legacy `/chat` trả HTTP 410.
- Mọi route Backend reload role/department từ `ProfileDB`, không quyết định quyền bằng claim JWT stale.
- Có API/UI quản trị role + department, capability catalog và `audit_logs`.
- Full regression, frontend build, live retrieval eval và guardrail đều đạt kết quả nêu tại mục 4.

Hệ thống đã đủ nền an toàn để tiếp tục quản trị phân quyền và vận hành RAG. Tuy nhiên, **target Enterprise Doc Intelligence trong báo cáo chưa hoàn thành**: generic Structured Knowledge extraction, Evidence/Relation runtime, cross-document reasoning và HITL review vẫn là P1/P2.

## 2. Đối chiếu các critical findings

| Finding gốc | Trạng thái hiện tại | Evidence / thay đổi |
|---|---|---|
| R-01 — write path không tenant-safe | **CLOSED trong workspace** | Chunk ID có tenant; collection tách theo tenant+domain; delete bắt buộc tenant; raw/processed/chunks vào thư mục tenant; rebuild bắt buộc tenant; test hai tenant cùng filename/stem. |
| R-02 — runtime upload không vào ACL | **CLOSED trong workspace** | Upload mặc định `RESTRICTED`; lưu owner/department/scope/role/source/lifecycle trong DB và Chroma; retrieval tách nhánh COMPANY_WIDE/DEPARTMENT/ROLE/RESTRICTED fail-closed. |
| R-03 — identity fail-open/default | **CLOSED trong workspace** | `AgentQueryRequest` và `UserContext.from_state` bắt buộc tenant/user/department/role; role lạ bị từ chối; legacy `/chat` bị vô hiệu hóa. |
| R-04 — JWT role stale | **CLOSED trong workspace** | `get_current_user` reload `ProfileDB` mỗi request. Test chứng minh claim giả `SUPER_ADMIN` không nâng quyền nếu DB là `HR_ADMIN`. |
| R-05 — Structured Knowledge hardcoded/DB trống | **OPEN — P1** | `src/knowledge/` và vertical-slice tests vẫn chỉ phục vụ hai document hardcoded; chưa được gọi từ live ingestion/agent graph. |
| R-06 — held-out/eval cũ fail | **PARTIALLY CLOSED** | Retrieval datasets/qrels đã align và retrieval metrics hiện đạt tốt; guardrail sạch. Chưa rerun answer-level held-out 30 câu theo đúng benchmark mới nên không tuyên bố đóng toàn bộ R-06. |
| R-07 — documentation stale | **PARTIAL** | Báo cáo đối chiếu này cập nhật nguồn sự thật mới; README/ARCHITECTURE/JOURNAL vẫn cần consolidation riêng. |
| R-08 — path/repo hygiene | **PARTIAL/OPEN** | Các path mới tenant-safe và config-driven; workspace vẫn dirty, có `.worktrees/` user-owned và nhiều artifact eval chưa commit. |
| R-09 — Monitoring/HITL UI missing | **PARTIAL** | Đã có UI quản trị quyền/audit. Monitoring và HITL knowledge review vẫn chưa nối. |

## 3. Kiến trúc hiện tại sau remediation

### Data path

```text
Admin upload
  → DocumentDB (tenant + ACL + lifecycle + owner)
  → signed internal ingestion job
  → tenant/raw + tenant/processed
  → chunking (tenant-qualified IDs)
  → FPT embedding
  → tenant/domain-specific Chroma collection
  → tenant/chunks artifact for rebuild
```

Runtime Chroma ACL không phụ thuộc CSV registry. CSV vẫn là SoT của corpus offline. Các filter ACL được chia thành nhiều query độc lập rồi merge/deduplicate vì Chroma Cloud giới hạn tối đa 8 predicate/query; mỗi query hiện không vượt quota.

### Read path

```text
JWT → ProfileDB reload → Backend signed identity → Agent
  → domain router (HR/Core | Accounting | Product)
  → tenant/domain collection
  → registry branch + runtime ACL branches (parallel)
  → merge by chunk ID / best distance
  → hybrid/rerank/generation/guardrail/citation
```

### Permission administration

- `HR_ADMIN`: xem access model và danh sách user; quản lý document/index/eval theo role hiện hữu.
- `SUPER_ADMIN`: đổi role/department, xem audit log.
- Role/department có hiệu lực từ ProfileDB ở request tiếp theo; JWT claim cũ không thể tự nâng quyền.
- Thay đổi role/department ghi `USER_ACCESS_UPDATED`; thay đổi document ACL ghi `DOCUMENT_ACL_UPDATED`.

## 4. Kết quả xác minh

### Automated regression

| Suite | Kết quả |
|---|---:|
| Agent/root tests | **521 passed + 6 subtests** |
| Backend tests | **110 passed** |
| Frontend production build | **PASS** |
| Live Chroma cutover smoke | **49 passed** trong nhóm retrieval/domain/smoke |

Backend test còn warning kỹ thuật không làm fail suite: test JWT secret ngắn, deprecation của Starlette/httpx và aiosqlite thread cleanup trong durability test.

### Live retrieval — post ACL

| Domain | Dataset/split | Kết quả chính |
|---|---|---|
| HR/Core | 29 in-scope, top-10 | Hit@10 **89.7%**, Recall@10 **88.1%**, nDCG@10 **0.749**, Doc Hit@10 **100%** |
| Accounting | heldout, 5 in-scope + 1 no-GT, top-5 | Hit@5 **100%**, Recall@5 **76.7%**, nDCG@5 **0.525**, Doc Hit **100%** |
| Product | 15 in-scope + 1 OOS, top-10 | Mean Recall@10 **88.9%**, mean nDCG@10 **0.678** |

Các con số giữ nguyên baseline trước remediation, cho thấy tenant/ACL/identity changes không làm giảm retrieval quality.

### Guardrail — FPT Cloud judge x3 votes/turn

| Domain | Kết quả |
|---|---:|
| HR/Core | **7/7 PASS**, 0 agent fail, 0 judge uncertain |
| Accounting | **5/5 PASS**, 0 agent fail, 0 judge uncertain |
| Product | **5/5 PASS**, 0 agent fail, 0 judge uncertain |

## 5. Artifacts và migration mới

- `supabase/migrations/0008_document_runtime_acl.sql`
- `supabase/migrations/0009_access_admin_audit.sql`
- `backend/app/api/v1/endpoints/admin.py`
- `backend/app/domain/models/audit.py`
- `frontend/components/AccessAdmin.tsx`
- `tests/test_workers/test_tenant_write_isolation.py`
- `backend/tests/test_admin_access.py`
- `eval/results/*_post_acl_20260822.json`

## 6. Có thể bắt đầu phân quyền chưa?

**Có.** P0 tenant isolation, runtime ACL, strict identity và DB-backed authorization đã hoàn tất trong workspace; phần quản trị role/department + audit cũng đã được triển khai và test.

Trước khi cho người dùng production sử dụng, cần thực hiện release checklist:

1. Review và apply migration 0008–0009 lên Supabase theo quy trình change management.
2. Cấu hình secret production tối thiểu 32 bytes và đảm bảo Backend/Agent dùng cùng service token HMAC.
3. Commit/review/deploy workspace hiện tại; chạy migration smoke và full test trong CI/CD.
4. Test upload thật trên môi trường staging: owner allow, stranger deny, department/role exact, archive/reindex deny.
5. Sao lưu/rollback plan cho schema và Chroma artifacts.

## 7. Phần tiếp theo đúng dependency chain

1. Generic LLM Structured Knowledge extraction cho ≥10 document thật.
2. Persist Knowledge Item + Evidence span/hash theo Document Version trong Postgres.
3. Relation detection (`SUPERSEDES`, `CONFLICTS_WITH`, `REFERENCES`).
4. Wire structured resolver/cross-document reasoning vào Agent.
5. HITL review API/UI và extraction/relation eval.
6. Consolidate README/ARCHITECTURE/JOURNAL, triển khai monitoring và production deploy pipeline.

## 8. Command declined trước đó có ảnh hưởng không?

Không. Lần command bị declined/failed là lỗi khởi tạo sandbox helper; lệnh chưa chạy nên không ghi/xóa dữ liệu. Các thao tác cần thiết sau đó được chạy lại bằng quyền đã cho, có compile/test/eval xác minh. Không có bằng chứng Chroma bị mutate ngoài các đợt ingestion đã chủ động thực hiện trước đó; các eval trong đợt đối chiếu này chỉ query Chroma read-only.