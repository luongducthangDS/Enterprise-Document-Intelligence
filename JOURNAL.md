# Weekly Journal — Team [Tên Team]

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
- [ ] Chạy release held-out mới sau khi được phép gửi bộ câu hỏi synthetic tới dịch vụ model/vector bên ngoài.

### Đã hoàn thành
- G5 `qa_013`/`qa_122` lấy đúng evidence sau khi canonical hóa retrieval query.
- Repo migration tái dựng đủ 10 bảng; chuỗi migration liên tục `0001`–`0007`.
- Supabase release có RLS đầy đủ và trigger chặn tự nâng `role/access_level/manager_id`.
- Backend không còn để worker kẹt `QUEUED`: submit sang Agent, poll trạng thái và persist kết quả/metric thật.
- Regression offline: 421 test core và 106 test backend đều pass; root Ruff sạch.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Backend chỉ tạo job nhưng không thực thi | Thêm WorkerJobClient và đồng bộ kết quả khi FE poll | Ba lifecycle có test tới trạng thái terminal |
| Migration RLS cũ không thể chạy lại vì policy trùng tên | Thêm migration `0007` idempotent, phạm vi đúng ba bảng worker + profile guard | Apply và verify trực tiếp thành công |
| Sandbox chặn kết nối FPT.AI/Chroma Cloud | Phân loại run 0/30 là lỗi hạ tầng, không báo như quality score | Chờ xác nhận data egress để chạy release eval hợp lệ |

### Bài học
- Không coi `QUEUED` trong DB là worker đã hoàn thiện; phải chứng minh cả submit, polling, terminal state và persistence.
- Kết quả eval chỉ hợp lệ khi không có lỗi hạ tầng; 0% do socket bị chặn không phải 0% chất lượng.
- Migration vá production nên idempotent và giới hạn phạm vi, đặc biệt khi schema đã tồn tại trước lịch sử migration trong repo.

### Kế hoạch tuần sau
- Chạy đúng một release held-out hợp lệ sau khi được duyệt data egress và ghi số liệu trung thực.
- Peer review chéo: Dương review phần minhphu trước khi merge `develop`.

---

<!-- Tiếp tục copy block trên cho Week 4, 5, 6 -->
