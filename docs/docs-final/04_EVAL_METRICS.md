# Báo cáo Metrics & Evaluation cuối — Toàn bộ hệ thống P-153

**Baseline:** `develop@87a85aa34cc23e41cd2c6d8a1eb4331e31a79300`

**Ngày đánh giá:** 2026-09-01

**Phạm vi:** Frontend, Backend/API, Agent/RAG, dữ liệu, bảo mật/RBAC, tích hợp, kiểm thử thủ công, chất lượng mã và triển khai

**Kết luận:** **CONDITIONALLY READY — chưa đủ điều kiện tuyên bố Full Release Verified**

**Artifact tổng hợp:** [`final_system_evaluation_20260901.json`](../../eval/results/final_system_evaluation_20260901.json)

## 1. Scorecard toàn hệ thống

| Khu vực | Kết quả hiện tại | Trạng thái |
|---|---|:---:|
| Frontend quality | Lint PASS; typecheck PASS; production build PASS | PASS |
| Frontend dependency security | 5 vulnerabilities: 3 High, 2 Moderate | FAIL |
| Backend/API regression | 152 passed; 0 failed/error; 10 warnings; 16.326 giây | PASS |
| Agent/core full suite | 589 passed; 44 skipped; 6 failed; 8 errors; 6 subtests pass | FAIL |
| Security/safety targeted suite | 39 passed + 6 subtests | PASS |
| Boundary/role/action regression | 68/68 đúng; 0 invariant violation | PASS |
| Cross-department ACL | 15/15 truy cập trái quyền bị chặn | PASS |
| Dataset self-contained checks | 29 query/29 qrel; 68 QA items; không có general local chunks | PARTIAL |
| Product retrieval alignment | 0/26 unique gold chunk IDs tồn tại | FAIL |
| Current live retrieval/answer quality | Chưa đo được trên baseline hiện tại | NOT RUN |
| Manual acceptance | 6/7 PASS; TC04 FAIL; 32 evidence cells lỗi | INCOMPLETE |
| Python static quality | Root 150 Ruff findings; Backend 78 | FAIL |
| Docker/deployment config | Thiếu `DATABASE_URL` trong môi trường kiểm chứng | ENV BLOCKED |
| Live E2E/migration parity | Cần Chroma/model/database target hoạt động | ENV BLOCKED |

Không tính trung bình các hàng trên thành một “system accuracy” duy nhất vì chúng đo các thuộc tính khác nhau. Trạng thái tổng thể dựa trên gate: chỉ cần security dependency, regression, data alignment hoặc live acceptance chưa đạt thì chưa được gắn `FULLY VERIFIED`.

## 2. Frontend

Chạy từ `frontend/` với lockfile hiện tại:

| Gate | Kết quả |
|---|---:|
| `pnpm lint` | PASS |
| `pnpm typecheck` | PASS |
| `npm run build` | PASS |
| Next.js | 15.5.23 |
| Compile time | 21.0 giây |
| Route `/` size | 33.9 kB |
| First Load JS `/` | 136 kB |
| Shared First Load JS | 103 kB |

`pnpm audit --audit-level high` trả exit code 1: **5 vulnerabilities**, gồm **3 High** và **2 Moderate**. High advisories đi qua các dependency bắc cầu `next > sharp` và `next > postcss`. Do đó frontend compile được nhưng dependency-security gate chưa đạt.

## 3. Backend, API và database

Backend pytest hiện tại:

| Passed | Failed | Errors | Skipped | Warnings | Thời gian |
|---:|---:|---:|---:|---:|---:|
| 152 | 0 | 0 | 0 | 10 | 16.326s |

Raw JUnit: [`final_backend_pytest_20260901.xml`](../../eval/results/final_backend_pytest_20260901.xml).

Các test bao phủ auth, chat/conversation, citation, document, ticket, review, worker và service/API contracts. Có 12 file migration Supabase trong repository. Tuy nhiên chưa xác nhận việc apply migration trên database đích; migration parity live bị chặn bởi dependency Chroma/network. `docker compose config -q` cũng chưa validate được vì môi trường hiện tại thiếu `DATABASE_URL`.

## 4. Agent/core và tích hợp

| Passed | Skipped | Failed | Errors | Subtests passed | Pass rate trên test không skip |
|---:|---:|---:|---:|---:|---:|
| 589 | 44 | 6 | 8 | 6 | 97.68% |

Suite vẫn là **FAIL**; pass rate không thay thế điều kiện zero-failure.

- 8 errors ở migration parity do không kết nối được Chroma Cloud.
- 4 failures ở production cutover smoke do FPT/Chroma live không khả dụng.
- 2 failures ở LLM config do credential/provider từ environment làm unit test không còn hermetic.

Raw log của full root suite **không được lưu** vì output assertion có chứa giá trị credential. Báo cáo chỉ giữ aggregate và nguyên nhân đã được làm sạch. Đây đồng thời là một finding về bảo mật log và isolation cấu hình.

## 5. Bảo mật, RBAC và boundary

| Metric | Kết quả | Wilson 95% CI | Diễn giải |
|---|---:|---:|---|
| Security/safety/evaluation tests | 39 passed + 6 subtests | — | Regression subset cho ACL, guardrail và metric calculation |
| Cross-department ACL fail-closed | 15/15 = 100% | 79.61%–100% | Toàn bộ ca truy cập chéo phòng ban trong bộ test bị chặn |
| Boundary scenario accuracy | 68/68 = 100% | 94.65%–100% | Mapping deterministic của scenario registry |
| Boundary invariant violations | 0 | — | Không vượt human-first/critical invariant trong fixture |

Đây là regression accuracy trên bộ deterministic, không phải penetration-test coverage hoặc production accuracy. Raw boundary artifact: [`final_boundary_20260901.json`](../../eval/results/final_boundary_20260901.json).

## 6. Dữ liệu, ingestion, HITL và RAG

- General dataset integrity tự thân hợp lệ: 29 retrieval queries, 29 qrel records và 68 QA eval items; không có held-out QA item và không có `data/chunks` cục bộ để đối chiếu retrieval live.
- HITL fixture schema completeness: 5/5. Đây là độ đầy đủ dữ liệu expected, **không phải model extraction accuracy**.
- Operations fixture completeness: 18/18. Đây là độ đầy đủ question/answer/context/source, **không phải agent answer accuracy**.
- Product qrel/corpus alignment: 0/26 unique gold chunk IDs có mặt. Vì alignment bằng 0%, Recall/nDCG Product hiện tại là không hợp lệ và không được báo thay bằng số cũ.
- Router dev 68 câu chưa chạy vì cần gửi dataset tới model API ngoài; phiên này không có quyền truyền dataset ra ngoài.
- Live retrieval, citation grounding và agent answer accuracy chưa chạy vì cần index Chroma/corpus/model provider đồng bộ với commit.

## 7. Kiểm thử thủ công và E2E

Workbook hiện có 7 test cases: **6 PASS, 1 FAIL (TC04)**. Có 32 ô evidence hiển thị `#VALUE!`, nên đây là record chưa hoàn chỉnh, không phải bằng chứng nghiệm thu cuối. TC04 liên quan yêu cầu mơ hồ “nghỉ 3 ngày tuần sau”.

Live E2E toàn stack chưa được chạy lại trên commit hiện tại. Báo cáo live ngày 22/08 và remediation sau đó chỉ là lịch sử, không được suy rộng sang baseline 01/09.

## 8. Hiệu năng và chất lượng AI — chỉ tham khảo lịch sử

Các số sau thuộc artifact cũ và **không phải current gate**:

| Baseline lịch sử | Metric | Giá trị |
|---|---|---:|
| Retrieval 19/08, dev n=27 | Hit@5 / Recall@5 / nDCG@5 | 96.3% / 89.5% / 0.819 |
| Retrieval 19/08, dev n=27 | Hit@10 / Recall@10 / nDCG@10 | 100% / 98.1% / 0.853 |
| Retrieval 19/08, dev n=27 | Multi-chunk Recall@10 / MRR | 96.3% / 0.849 |
| Router holdout đã consumed | Accuracy | 66/70 = 94.3% |
| E2E performance 13/08, n=35 | p50 / p95 / mean | 11.571s / 33.909s / 17.861s |
| E2E performance 13/08, n=35 | >30s / retry rate | 8.6% / 2.9% |

Router set đã bị đánh dấu `CONSUMED`, vì vậy không còn là held-out gate độc lập.

## 9. Static quality và deployment readiness

| Check | Kết quả |
|---|---:|
| `ruff check src tests --statistics` | 150 findings |
| Backend `ruff check app tests --statistics` | 78 findings |
| `docker compose config -q` | Environment blocked: thiếu `DATABASE_URL` |

Ruff findings phần lớn là import/format/modernization, nhưng có finding `F821 undefined-name`; vì vậy static gate được đánh FAIL, không chỉ warning. Deployment chưa được xác nhận cho tới khi compose config và target services được kiểm tra bằng biến môi trường hợp lệ.

## 10. Điều kiện để đạt `FULLY VERIFIED`

1. Nâng/cập nhật dependency để audit không còn High vulnerability, hoặc có risk acceptance được ghi nhận.
2. Cô lập environment trong LLM config tests; tách/marker hóa cloud tests để offline suite chạy zero-failure.
3. Xử lý Ruff findings, ưu tiên `F821` và lỗi có ảnh hưởng runtime.
4. Khôi phục corpus/index đúng version, đạt qrel alignment 100%, rồi chạy retrieval, grounding và agent-answer eval hiện tại.
5. Chạy live Backend + Agent + PostgreSQL + Chroma + model provider và lưu artifact E2E/migration parity.
6. Sửa hoặc chấp nhận TC04; thay 32 evidence cells lỗi bằng screenshot/log có thể truy vết.

## 11. Lệnh tái lập chính

```powershell
# Backend
cd backend
python -m pytest tests -q --junitxml=../eval/results/final_backend_pytest_20260901.xml
ruff check app tests --statistics

# Agent/core
cd ..
python -m pytest tests -q
ruff check src tests --statistics

# Frontend
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
npm run build
pnpm audit --audit-level high

# Offline AI/security/data artifacts
cd ..
python eval/scripts/eval_final_offline.py --out eval/results/final_offline_eval_20260901.json
python eval/scripts/eval_boundary.py --out eval/results/final_boundary_20260901.json
python eval/scripts/check_dataset_integrity.py
python eval/scripts/check_product_dataset_integrity.py
```

## 12. Câu trình bày ngắn với mentor

> Nhóm đã đánh giá lại toàn bộ P-153 trên `develop@87a85aa`: frontend lint/typecheck/build đều pass; backend đạt 152/152 test; security/boundary/ACL đạt toàn bộ bộ regression hiện có. Hệ thống hiện ở mức Conditionally Ready, chưa phải Fully Verified vì root Agent suite còn 14 failure/error chủ yếu từ live cloud và config isolation, frontend audit còn 3 High + 2 Moderate vulnerabilities, Ruff còn findings, Product qrel không khớp corpus và E2E/manual evidence chưa được chốt lại. Các metric AI lịch sử được tách riêng, không dùng thay cho kết quả baseline hiện tại.
