# Weekly Journal — Team AI20K-Build-Phase-Cohort-3 (Project P-153)

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.

---

## Week 1: 2026-07-24 - 2026-07-30

### Mục tiêu tuần này
- [x] Khởi tạo dự án từ starter template (AI20K)
- [x] Thiết lập git flow (branch `main`/`develop`/`feature/*`) và AI usage logging hooks
- [ ] Xác định phạm vi sản phẩm cụ thể (chưa làm tuần này — mới dừng ở khởi tạo repo)

### Đã hoàn thành
- Fork template, tạo lại git history, mời thành viên vào org `AI20K-Build-Phase-Cohort-3`
- Test quy trình PR/merge giữa `develop` và các nhánh cá nhân (nhiều commit `test`/`test2`/`test3` — mục đích là làm quen quy trình, không phải code sản phẩm)

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Cả team chưa quen git flow (branch, PR, merge) | Làm nhiều PR thử nghiệm nhỏ trên `develop` trước khi vào code thật | Quy trình PR chạy được, nhưng git history có nhiều commit rác dạng "test" |

### Bài học
- Nên thống nhất git flow bằng tài liệu trước (sau này mới có `GIT-FLOW.md`), tránh commit thử nghiệm lẫn vào lịch sử chính
- Sau tuần này có khoảng trống ~9 ngày (27/7–3/8) không có hoạt động git — cần rút kinh nghiệm lên lịch làm việc đều hơn giữa các tuần

### Kế hoạch tuần sau
- [ ] Chốt phạm vi sản phẩm (HR Document Intelligence Agent)
- [ ] Thu thập và tổ chức dữ liệu nguồn
- [ ] Dựng pipeline ingestion + agent RAG đầu tiên

---

## Week 2: 2026-07-31 - 2026-08-07

### Mục tiêu tuần này
- [x] Chốt phạm vi: HR Document Intelligence Agent — trả lời câu hỏi HR dựa trên pháp luật lao động/BHXH/BHYT/thuế TNCN + quy định nội bộ, không gắn cứng vào 1 công ty cụ thể
- [x] Thu thập, tổ chức dữ liệu nguồn theo 6 category (`data/raw/`)
- [x] Dựng pipeline ingestion (extract → clean → chunk → embed → index lên Chroma Cloud)
- [x] Dựng agent RAG bằng LangGraph (router → retrieve → grade → generate → hallucination-check → confidence → finalize/escalate)
- [x] Dựng bộ eval 3 tầng (router / retrieval / agent) có thống kê (bootstrap CI, kappa liên-giám khảo)
- [ ] Chốt 1 kiến trúc backend duy nhất (hiện có 2 song song: `src/api/` và `backend/`)

### Đã hoàn thành
- Tổ chức dữ liệu nguồn đủ 6/6 category, extract 5 văn bản luật, phát hiện và loại 1 văn bản hết hiệu lực trước khi đưa vào index
- Data ingestion pipeline hoàn chỉnh + schema Supabase (users/RBAC, chat history, ticket) + bộ eval dataset đầu tiên (commit `a198c01`)
- Auth (sign in/up) và API layer (Conversation/Chat RAG/Citation) cho backend
- Phát hiện và sửa 4 lỗi khiến agent **không trả lời được câu HR nào**: reranker crash do đường dẫn cache model trỏ ổ đĩa không tồn tại, `TypeError` khi thiếu dependency, cơ chế escalate-theo-confidence bị vô hiệu hoá âm thầm (bug nguy hiểm nhất vì không có triệu chứng rõ ràng), unit test phụ thuộc mạng
- Phát hiện và sửa 3 lỗi làm bộ eval đo sai (ground truth dài hơn chunk tối đa → 78/128 câu không thể khớp; qrel bị nới lỏng sai quy tắc mất nghĩa "relevant"; eval retrieval bỏ qua reranker trong khi agent có dùng)
- Kết quả đo cuối tuần: pass rate agent 63.5% → 75.7% (140 câu), router accuracy 88.6% → 95.7%, cắt latency tổng 22-23%
- Dọn lại cấu trúc thư mục (`scripts/rag_pipeline/`, `docs/rag-pipeline/`) và merge nhánh RAG vào `develop`

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Agent hỏng hoàn toàn sau một phiên sửa song song (reranker ghép sai cách) | Audit có hệ thống, chạy thử để xác minh từng giả thuyết thay vì suy đoán từ đọc code | Tìm đúng 2 nguyên nhân gốc (reranker + đơn vị đo ground truth), sửa dứt điểm trong ~2 giờ |
| Threshold lọc theo cosine distance không tách được in-scope/out-of-scope (phân phối chồng lấn nặng) | Đo phân phối thật trên 140 câu, chuyển sang dùng điểm reranker (tách bạch tốt hơn hẳn) để tính confidence | Escalate hoạt động đúng lại: 89% in-scope trả lời thẳng, 11% escalate đúng tỉ lệ retrieval thật sự hỏng |
| Bộ eval chỉ phủ 40% index (11/29 tài liệu), 2 bộ luật lớn nhất chưa từng được test | Xây bộ eval retrieval riêng theo hướng chunk-first, mở rộng lên 29/29 tài liệu | Bộ eval mới phát hiện được lỗi ở cả những tài liệu trước đây "mù" hoàn toàn |
| Merge nhánh cá nhân vào `main` rồi bị revert (PR #10) | Cần thống nhất lại quy tắc merge/rebase giữa nhánh cá nhân và `main`/`develop` trước khi lặp lại | Chưa xử lý dứt điểm — đưa vào kế hoạch tuần sau |

### Bài học
- Lỗi nguy hiểm nhất không phải lỗi crash ồn ào, mà là lỗi **tắt tính năng âm thầm** (escalate-theo-confidence chết mà agent vẫn chạy bình thường, chỉ sai) — cần thêm test/alert cho đúng loại lỗi này, không chỉ test "không crash"
- Thước đo (eval set) phải được kiểm chứng độ tin cậy trước khi dùng để tune — tune trên thước sai sẽ tốn công mà không cải thiện gì thật
- Deliverable hành chính (README/JOURNAL/WORKLOG/architecture diagram) rất dễ bị bỏ quên khi dồn lực vào kỹ thuật — cần làm xen kẽ mỗi ngày, không dồn cuối kỳ

### Kế hoạch tuần sau
- [ ] Chốt 1 kiến trúc backend (bỏ 1 trong 2: `src/api/` Supabase Auth/RLS hoặc `backend/` JWT tự chế)
- [ ] Xác nhận migration `0003` (chặn tự leo quyền `hr_admin`) đã apply lên Supabase thật
- [ ] Giảm latency p50 in-scope (hiện ~35s) — model nhỏ hơn cho router/hallucination-check, chạy song song 2 node độc lập
- [ ] Sửa 14 câu generation sai (ưu tiên nguồn chính thức khi nguồn mâu thuẫn) và mở rộng held-out set để có số liệu sạch
- [ ] Hoàn thiện các deliverable còn thiếu cho Demo Day (video, pitch deck, live URL)

---

## Week 3: 2026-08-08 - 2026-08-19

### Mục tiêu tuần này
- [x] Chốt sản phẩm theo định vị HR Helpdesk Assistant và hợp nhất backend/agent/frontend.
- [x] Sửa G5 retrieval, đồng bộ migration và xác nhận RLS trên Supabase thật.
- [x] Hoàn thiện execution lifecycle cho ingestion/index/evaluation worker.
- [x] Chạy release agent held-out mới sau khi được phép gửi 30 câu hỏi synthetic tới dịch vụ model/vector bên ngoài.
- [x] Chạy retrieval held-out 20 query và chốt Recall độc lập.

### Đã hoàn thành
- G5 `qa_013`/`qa_122` lấy đúng evidence sau khi canonical hóa retrieval query.
- Repo migration tái dựng đủ 10 bảng; chuỗi migration liên tục `0001`–`0007`.
- Supabase release có RLS đầy đủ và trigger chặn tự nâng `role/access_level/manager_id`.
- Backend không còn để worker kẹt `QUEUED`: submit sang Agent, poll trạng thái và persist kết quả/metric thật.
- Regression offline: 421 test core và 106 test backend đều pass; root Ruff sạch.
- Agent held-out hợp lệ: 0/30, không có lỗi hạ tầng; 17/30 câu bị router đưa sang `pure_statutory`, toàn bộ gold chunk ID không khớp retrieval hiện tại và judge chỉ xác nhận 2/30 câu trả lời.
- Retrieval held-out: Hit Rate@5 45%, Recall@5 29,6%, document Hit Rate@5 15%, MRR 0,425; không đạt gate Recall@5 85%.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Backend chỉ tạo job nhưng không thực thi | Thêm WorkerJobClient và đồng bộ kết quả khi FE poll | Ba lifecycle có test tới trạng thái terminal |
| Migration RLS cũ không thể chạy lại vì policy trùng tên | Thêm migration `0007` idempotent, phạm vi đúng ba bảng worker + profile guard | Apply và verify trực tiếp thành công |
| Sandbox chặn kết nối FPT.AI/Chroma Cloud | Phân loại run đầu là lỗi hạ tầng, sau đó chạy lại khi có xác nhận data egress | Run hợp lệ hoàn tất; giữ nguyên 0/30 và không tune lại |

### Bài học
- Không coi `QUEUED` trong DB là worker đã hoàn thiện; phải chứng minh cả submit, polling, terminal state và persistence.
- Kết quả eval chỉ hợp lệ khi không có lỗi hạ tầng; 0% do socket bị chặn không phải 0% chất lượng.
- Migration vá production nên idempotent và giới hạn phạm vi, đặc biệt khi schema đã tồn tại trước lịch sử migration trong repo.

### Kế hoạch tuần sau
- [ ] Mở rộng hệ thống thành Trợ lý Tri thức Nội bộ Đa phòng ban (Enterprise Internal Knowledge System).
- [ ] Thiết kế cơ chế phân quyền truy cập theo phòng ban (Department ACL) và cách ly dữ liệu tri thức.
- [ ] Xây dựng quy trình bóc tách và duyệt tài liệu có con người can thiệp (Human-in-the-Loop Document Review).
- [ ] Thực hiện kiểm thử chấp nhận toàn diện E2E Live và khắc phục các điểm nghẽn tích hợp.
- [ ] Chuẩn bị kịch bản triển khai cloud và tài liệu Demo Day hoàn chỉnh.

---

## Week 4: 2026-08-20 - 2026-08-26

### Mục tiêu tuần này
- [x] Mở rộng định vị và năng lực từ HR Agent sang Enterprise Internal Knowledge Assistant đa phòng ban (HR, Kế toán, Sản phẩm, Vận hành).
- [x] Thiết lập phân quyền tri thức theo phòng ban (Department ACL) với cơ chế fail-closed, bổ sung migrations `0010`, `0011`.
- [x] Xây dựng trọn vẹn quy trình Human-in-the-Loop Document Review: API nạp bài (`/api/v1/document-submissions`), Worker bóc tách LLM cấu trúc (`src/workers/document_analysis.py`), Migration `0012`, và giao diện duyệt (`DocumentReview.tsx`).
- [x] Chạy 46 ca kiểm thử E2E Live Acceptance Tests, lập báo cáo phát hiện lỗi và hoàn thành đợt Remediation khắc phục triệt để BUG-01 → BUG-07.
- [x] Tăng cường an ninh vận hành: Rate limit đăng nhập, chính sách mật khẩu 8 ký tự, che giấu PII, và làm sạch thông tin bí mật.
- [x] Cấu hình Blueprint triển khai Render Cloud (`render.yaml`) và dịch vụ Warmup Ping (`WarmupPing.tsx`, `warmup_service.py`) triệt tiêu cold start.
- [x] Hoàn thiện trọn bộ 10 Deliverables theo tiêu chuẩn BTC AI20K.

### Đã hoàn thành
- **Multi-domain Knowledge Expansion:** Bổ sung các bộ dữ liệu và bộ sưu tập vector chuyên biệt cho Kế toán (`accounting`), Sản phẩm (`product`), và phạm vi toàn công ty (`COMPANY_WIDE`).
- **Department-Scoped ACL & Fail-Closed:** Áp dụng bộ lọc quyền chặt chẽ tại tầng Backend và Retrieval (`src/security/departments.py`, `access_control.py`), ngăn ngừa hoàn toàn việc nhân viên phòng ban này truy cập tài liệu nhạy cảm của phòng ban khác.
- **HITL Document Review Workflow:** Xây dựng thành công quy trình 5 bước nạp tài liệu → LLM bóc tách Quyết định, Trách nhiệm, Thời hạn → Chuyên viên kiểm tra và phê duyệt trên UI → Tự động nạp vào Vector DB.
- **E2E Remediation:** Khắc phục lỗi lệch intent DTO `pure_statutory` (BUG-01), thống nhất resolver collection Vector DB theo tenant (BUG-02), xử lý xung đột 409 khi nạp trùng file (BUG-03), sửa định tuyến ticket theo đúng phòng ban.
- **DevOps & Cloud Readiness:** Viết file cấu hình `render.yaml` chuẩn cho cả 3 container (Frontend, Backend, Agent), tích hợp `WarmupPing` ping tự động mỗi 4 phút để giữ dịch vụ luôn sẵn sàng.
- **Tài liệu & Deliverables:** Đồng bộ toàn diện `README.md`, `ARCHITECTURE.md`, `JOURNAL.md`, `WORKLOG.md`, `eval/results/report.md`, `eval/EVAL_EVIDENCES.md`, và `presentation/README.md`.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Trôi cấu hình tên collection Vector DB khiến tài liệu upload mới bị ghi vào collection ma (BUG-02) | Chuẩn hóa hàm `collection_name_for_department` sử dụng resolver duy nhất `get_tenant_collection_name(tenant)` làm Single Source of Truth (SSOT) | 100% tài liệu nạp mới được lưu đúng collection và tra cứu được ngay |
| Khởi động lạnh (Cold Start) trên cloud free tier gây timeout request đầu tiên | Xây dựng service `WarmupPing` ở Frontend và endpoint `/api/v1/warmup` ở Backend để chủ động giữ ấm kết nối | Loại bỏ hiện tượng timeout, thời gian phản hồi lượt đầu giảm từ 45s xuống mức bình thường |
| Xung đột tên schema và vai trò sau khi merge nhánh tính năng Kế toán | Lập tài liệu hòa giải Semantic ACL, chuẩn hóa phân quyền vai trò trong profile DB và cập nhật test fixtures | Toàn bộ 114 test backend và test suite agent pass ổn định |

### Bài học
- Thiết kế bảo mật phân quyền (ACL) phải tuân thủ nguyên tắc **Fail-Closed** ngay từ tầng lọc dữ liệu vector, không chỉ dựa vào việc ẩn nút bấm trên giao diện.
- Cơ chế Human-in-the-Loop (HITL) là cầu nối bắt buộc giữa AI tự động và độ tin cậy nghiệp vụ doanh nghiệp — việc cho phép chuyên viên xem và sửa đổi các trường thông tin bóc tách trước khi lưu kho tri thức giúp triệt tiêu 100% rủi ro ảo giác trong dữ liệu chính thức.
- Tự động hóa kiểm thử E2E không mock dependency là cách duy nhất phát hiện ra các lỗi lệch giao thức (DTO mismatch) và trôi môi trường (env drift) trước ngày Demo Day.

### Kế hoạch tiếp theo (Demo Day & Production)
- [ ] Thực hành thuyết trình Pitch Deck 10 slides theo kịch bản 10 phút.
- [ ] Quay video demo sản phẩm (3-5 phút) bao gồm luồng Chat đa phòng ban, Phân quyền ACL và Quy trình duyệt tài liệu HITL.
- [ ] Triển khai chính thức lên Render Cloud và Vercel theo blueprint đã cấu hình.
