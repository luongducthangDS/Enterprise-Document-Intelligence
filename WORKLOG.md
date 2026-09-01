# Worklog từ lịch sử commit `develop` — P-153

**Nguồn chuẩn:** `git log develop --no-merges`
**Khoảng thời gian:** 2026-07-24 → 2026-08-31
**Baseline:** `87a85aa`

## Quy ước

- Chỉ ghi công việc có bằng chứng trong lịch sử commit của `develop`.
- Tên người được ánh xạ từ Git author: `minhphu711` → Giang Minh Phú; `hthanhson` → Hoàng Thanh Sơn; `duong` → Hoàng Thái Dương; `luongducthangws` → Lương Đức Thắng.
- Không suy luận số giờ làm việc từ commit.
- Merge commit không được tính như một công việc riêng để tránh ghi trùng nội dung.
- Commit SHA là khóa truy vết; mô tả bên dưới là nhóm hóa nội dung commit, không thay thế diff gốc.

## Tuần khởi tạo — 24/07 đến 26/07

| Ngày | Thành viên | Công việc có bằng chứng | Commit |
|---|---|---|---|
| 24/07 | Phoenix mentor bot | Khởi tạo repository | `0ebac15` |
| 25/07 | Giang Minh Phú | Khởi tạo dự án từ template và kiểm tra repository | `b92c575`, `0da5ca9`, `3fd9f93` |
| 26/07 | Hoàng Thanh Sơn | Các commit kiểm tra ban đầu cho quy trình Git | `2b8890f` → `f41c9c4` |

**Kết quả tuần:** Repository và baseline làm việc được hình thành.

## Tuần 1 — 03/08 đến 09/08

| Ngày | Thành viên | Công việc có bằng chứng | Commit |
|---|---|---|---|
| 04/08 | Hoàng Thái Dương | Khởi tạo giao diện từ template | `726c5c7` |
| 04/08 | Hoàng Thanh Sơn | Tạo cấu trúc Backend service; sửa AI logging | `5db3a8b`, `dcfc66e`, `9a90ca3` |
| 04/08 | Giang Minh Phú | Đồng bộ diagram, PRD và project brief | `4910c88` |
| 05/08 | Hoàng Thanh Sơn | Thêm đăng ký/đăng nhập | `f4a4feb` |
| 05/08 | Lương Đức Thắng | Xây dựng ingestion HR, Supabase schema và evaluation dataset; sửa setup hook | `a40668b`, `548c4a2` |
| 05/08 | Hoàng Thái Dương | Dựng demo UI workflow | `1e8b3af` |
| 05/08 | Giang Minh Phú | Đồng bộ và dọn tài liệu sinh tự động | `6eec74a`, `9d5d958` |
| 06/08 | Hoàng Thanh Sơn | Conversation API, Chat RAG API và Citation API | `7b82468` |
| 06/08 | Lương Đức Thắng | Hạ latency, thêm BM25/rerank/qrel evaluation và quality fixes | `6dc4628`, `55d9473`, `738a0a0` |
| 07/08 | Hoàng Thanh Sơn | Document/Ingestion, Index và Evaluation APIs | `f0b35d1` |
| 07/08 | Lương Đức Thắng | Tổ chức scripts/docs ingestion và eval; loại tài liệu cá nhân khỏi Git | `e362f51`, `7709b63` |
| 08/08 | Hoàng Thái Dương | Cải tiến frontend API workflows | `a6df0ad` |
| 08/08 | Giang Minh Phú | Đồng bộ docs và cấu hình Codex/Git ignore | `fc85c1a` → `b5359a0` |

**Kết quả tuần:** Có skeleton full-stack, auth/chat/document APIs, ingestion/RAG baseline và giao diện ban đầu.

## Tuần 2 — 10/08 đến 16/08

| Ngày | Thành viên | Công việc có bằng chứng | Commit |
|---|---|---|---|
| 10/08 | Giang Minh Phú | Tích hợp Backend với Agent service, chuẩn hóa Compose và tài liệu contract | `369016d`, `782a4f9`, `ea2dd15` |
| 11/08 | Hoàng Thái Dương | Cập nhật giao diện Frontend | `b01b9e2` |
| 11/08 | Giang Minh Phú | Migrate Frontend sang Next.js, thêm service vào Compose, harden Backend–Agent và Docker | `2ef6114`, `3e849e9`, `e01f2e6`, `0538b5e`, `df1fdb7`, `9d26b14`, `6d5bbd1`, `757a84c` |
| 11/08 | Lương Đức Thắng | Multi-turn, safety guardrails, streaming và citation `source_type` | `a4b00b3`, `5b70e75` |
| 11/08 | Hoàng Thanh Sơn | Sửa ticket authorization và thứ tự history chat | `df1fa96` |
| 12/08 | Hoàng Thanh Sơn | Mở rộng citation DTO với authority/source metadata | `98d4d02` |
| 13/08 | Giang Minh Phú | Khôi phục conversation/citation và cập nhật UI/ticket | `8435157`, `11fde9e` |
| 13/08 | Lương Đức Thắng | Thêm ingestion/index/evaluation workers | `857cee6` |
| 14/08 | Hoàng Thái Dương | Nâng cấp workflow và UI | `37db317` |
| 14/08 | Giang Minh Phú | Chuẩn hóa department, history/citation, ticket closure audit, dialog/UI và API docs | `006b328`, `0b5844b`, `1dac4e5`, `eca430c`, `91025a7`, `3028a8a` |
| 15/08 | Giang Minh Phú | Hoàn thiện README setup và sample queries | `0419757` |
| 16/08 | Lương Đức Thắng | Agent workers, boundary, taxonomy authority/provenance và Phase F eval | `8e0245e` |
| 16/08 | Hoàng Thanh Sơn | Cập nhật CI | `11017c9` |

**Kết quả tuần:** Ba service được tích hợp; Next.js, Backend–Agent contract, workers, multi-turn và guardrail trở thành luồng hệ thống thống nhất.

## Tuần 3 — 17/08 đến 23/08

| Ngày | Thành viên | Công việc có bằng chứng | Commit |
|---|---|---|---|
| 17/08 | Giang Minh Phú | Khôi phục ingestion/retrieval/eval assets, hòa giải migration/RLS, sửa retrieval và tổ chức test docs | `daf7ce3`, `b3e168a`, `66a4ffb`, `8e979b5`, `822834f` → `ea363be` |
| 18/08 | Hoàng Thanh Sơn | Sửa clarification loop | `deb03c2` |
| 19/08 | Hoàng Thanh Sơn | Harden chat recovery và ticket persistence | `01a6a67` |
| 19/08 | Giang Minh Phú | Worker lifecycle, security migration, held-out runs, benchmark/eval workflow và báo cáo post-MVP | `79b2fe0` → `c0bbc3a` |
| 21/08 | Hoàng Thanh Sơn | Bổ sung dữ liệu và accounting evaluation | `64572e7`, `4301120`, `3298463` |
| 21/08 | Giang Minh Phú | Product data/eval, post-MVP evaluation, bỏ secret/config local khỏi Git | `1a7872e`, `38f8273`, `42b67b7`, `a3c5738` |
| 21/08 | Lương Đức Thắng | Department ACL, taxonomy, legal authorization, system-data isolation, P1 vertical slice và docs | `37f7077`, `2389a84`, `e4123b0`, `52f8c13`, `de6e97b`, `0c41cbf`, `1a54615`, `5989376`, `c4da303`, `de923e3` |
| 22/08 | Hoàng Thanh Sơn | Accounting retrieval/guardrail/evaluation và giải quyết conflict retrieval | `d7c9934`, `79e2a7e`, `0e1e7cc`, `49e3e64` |
| 22/08 | Giang Minh Phú | Multi-domain RAG/ACL, routing và completion report | `02a72ca`, `72e75de`, `16ad92b` |
| 22/08 | Lương Đức Thắng | Live E2E, sửa agent contract/index/upload trace, remediation/audit reports và UX fix | `f4d8459`, `46f4dc6`, `87a8bb2`, `ff6b11a`, `c3a9bc0`, `170ccf6` |
| 23/08 | Hoàng Thanh Sơn | Knowledge architecture, Supabase knowledge layer/HITL, QC fixes và Render/warmup/static UI | `d46d950`, `9a276a2`, `db7887b`, `32b7b7a`, `a0fa71b`, `0b5eefd`, `22b4b01`, `4868eb4` |
| 23/08 | Giang Minh Phú | Harden department retrieval và bổ sung runtime database dependencies | `a084843`, `ab06bc7`, `b0670d6` |
| 23/08 | Lương Đức Thắng | Product/security audit, fail-closed ACL, UI upload, identity repositioning, CI security-ops | `650d29d`, `741109e`, `2a6b979`, `e162cb9`, `acd2409`, `766f0c3`, `b927da4` |

**Kết quả tuần:** Hệ thống mở rộng từ HR sang multi-domain, có ACL hai lớp, Supabase knowledge layer, live E2E/remediation và chuẩn bị deploy.

## Tuần 4 — 24/08 đến 30/08

| Ngày | Thành viên | Công việc có bằng chứng | Commit |
|---|---|---|---|
| 24/08 | Giang Minh Phú | Enforce department knowledge access; sửa department khi signup | `5766c9c`, `22a2ca8`, `4cf53a3` |
| 26/08 | Giang Minh Phú | Thêm document upload/review workflow | `c94a275` |
| 26/08 | Hoàng Thanh Sơn | Sửa ticket routing và Frontend gọi sai service | `5606e70`, `2857a88` |
| 26/08 | Lương Đức Thắng | Hoàn thiện docs/eval datasets và benchmark đa miền tại baseline thời điểm đó | `0f7c984` |
| 27/08 | Hoàng Thanh Sơn | Cập nhật source-answer UI/Backend, Chroma update scripts/dependencies, giảm latency, warmup và logging | `fdeff5d`, `a5cb1fe`, `e64297a`, `3345e57`, `7c3404a`, `4006b92`, `1d093f6`, `8fbd725` |
| 27/08 | Giang Minh Phú | Thêm multi-source product demo coverage; fail-fast/fallback khi LLM timeout | `b2c60c4`, `a350834` |
| 28/08 | Hoàng Thanh Sơn | Tối ưu response, tạo conversation và tắt ping Agent từ Backend health | `6291b00`, `2e315cc`, `49f1834` |
| 30/08 | Hoàng Thanh Sơn | Chuyển provider FPT/OpenAI và sửa upload/UI/Agent integration | `ce5abfa` |
| 30/08 | Giang Minh Phú | Hỗ trợ image upload và large documents | `a9cd61e` |

**Kết quả tuần:** Document review hoàn thiện hơn, chat nhanh hơn, provider linh hoạt hơn và upload hỗ trợ thêm ảnh/tệp lớn.

## Tuần 5 — 31/08

| Ngày | Thành viên | Công việc có bằng chứng | Commit |
|---|---|---|---|
| 31/08 | Hoàng Thanh Sơn | Versioning/soft archive tài liệu và overhaul review UI | `0a1aee0` |
| 31/08 | Hoàng Thanh Sơn | Cập nhật dependency Agent service | `2c52973` |
| 31/08 | Hoàng Thanh Sơn | Universal temporal query expansion, multi-turn coreference và PDF highlighting | `87a85aa` |

**Kết quả tuần:** Bổ sung lifecycle phiên bản tài liệu và các cải tiến truy xuất/đối soát cuối trên baseline bàn giao.

## Thống kê commit không tính merge

| Git author | Số commit trên `develop` trong giai đoạn |
|---|---:|
| `minhphu711` | 82 |
| `hthanhson` | 47 (43 với email hiện tại, 4 commit kiểm tra với email cũ) |
| `luongducthangws` | 35 |
| `duong` | 5 |
| `phoenix-mentor[bot]` | 1 |

Số commit chỉ dùng để truy vết hoạt động, không dùng làm thước đo năng suất hoặc mức đóng góp tương đối.
