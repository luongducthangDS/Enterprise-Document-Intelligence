# Weekly Journal — Team P-153

Nhật ký này tổng hợp theo tuần từ lịch sử commit của nhánh `develop`. Chi tiết theo ngày và SHA nằm tại [`WORKLOG.md`](WORKLOG.md).

## Tuần khởi tạo — 24/07 đến 26/07

### Mục tiêu

- Khởi tạo repository và xác nhận quy trình làm việc Git.

### Kết quả

- Repository được tạo từ template.
- Các commit kiểm tra ban đầu xác nhận thành viên có thể làm việc với remote.

### Bài học

- Cần sớm chuẩn hóa branch/commit convention để lịch sử sau này dễ truy vết.

## Tuần 1 — 03/08 đến 09/08

### Mục tiêu

- Dựng skeleton full-stack và phiên bản đầu của ingestion/RAG.
- Có auth, chat, document API và giao diện demo cơ bản.

### Kết quả

- Tạo Backend FastAPI với auth, conversation, chat, citation, document, ingestion, index và evaluation endpoints.
- Xây dựng ingestion pipeline, Supabase schema, datasets và retrieval evaluation.
- Có Frontend workflow ban đầu và cấu trúc triển khai.

### Khó khăn và xử lý

- Tài liệu và cấu hình công cụ cá nhân dễ bị commit nhầm; nhóm bổ sung ignore và dọn các file sinh tự động.
- Retrieval ban đầu cần thêm BM25/rerank/qrel để đo và cải thiện thay vì chỉ dựa vào cảm nhận.

### Bài học

- API contract, dữ liệu và bộ đo chất lượng phải phát triển song song với UI.

## Tuần 2 — 10/08 đến 16/08

### Mục tiêu

- Tích hợp Frontend–Backend–Agent thành một hệ thống.
- Hoàn thiện multi-turn, streaming, safety và worker lifecycle.

### Kết quả

- Frontend chuyển sang Next.js và được thêm vào Docker Compose.
- Backend gọi Agent qua contract rõ ràng; Agent có ingestion/index/evaluation workers.
- Bổ sung conversation history, citation provenance, guardrails và streaming.
- Chuẩn hóa Docker build, Supabase schema và tài liệu tích hợp.

### Khó khăn và xử lý

- Contract citation/history giữa ba tầng chưa đồng nhất; nhóm cập nhật DTO và integration mapping.
- Docker và database schema lệch môi trường; nhóm làm build reproducible và hòa giải schema.

### Bài học

- Tích hợp end-to-end cần contract test; unit test từng service không phát hiện hết lỗi mapping.

## Tuần 3 — 17/08 đến 23/08

### Mục tiêu

- Mở rộng từ HR sang tri thức nội bộ đa miền.
- Tăng cường ACL, evaluation, live E2E và chuẩn bị triển khai.

### Kết quả

- Bổ sung Accounting/Product datasets, domain routing và multi-domain retrieval.
- Thiết kế taxonomy authority/provenance/lifecycle và Department/Role ACL fail-closed.
- Kết nối worker lifecycle, sửa migration/RLS và tăng độ bền chat/ticket.
- Chạy live E2E tại baseline 22/08, ghi nhận BUG-01–07 và commit remediation.
- Thêm knowledge layer, extraction/HITL foundation, Render/warmup và UI upload.
- Thực hiện product/security/UX audit và pilot-readiness planning.

### Khó khăn và xử lý

- Lệch collection ghi/đọc, intent contract và upload duplicate chỉ lộ khi chạy E2E thật.
- Mở rộng domain tạo conflict semantics giữa category, department, authority và access scope; nhóm tách các trục metadata và kiểm tra quyền ở nhiều lớp.

### Bài học

- “Có test” chưa đủ; phải chạy qua hạ tầng và contract thật.
- Classification và authorization là hai bài toán khác nhau, không nên dùng chung một field.

## Tuần 4 — 24/08 đến 30/08

### Mục tiêu

- Hoàn thiện product sau mốc 24/08: review tài liệu, hiệu năng chat, upload và provider flexibility.

### Kết quả

- Siết department access và validation khi đăng ký.
- Hoàn thiện document upload/review workflow và sửa ticket/service URL integration.
- Bổ sung source-answer UI, script cập nhật Chroma và multi-source product coverage.
- Tối ưu warmup, logging, response và luồng tạo conversation; bỏ ping Agent trên mỗi Backend health request.
- Cho phép chuyển model provider giữa OpenAI và FPT.AI-compatible.
- Hỗ trợ upload ảnh và tài liệu lớn hơn.

### Khó khăn và xử lý

- Cold start và nhiều round-trip làm trải nghiệm chat chậm; nhóm hợp nhất các bước, dùng SSE và tối ưu transaction/warmup.
- Upload có nhiều đường file/URL/provider; nhóm bổ sung validation và fallback theo từng tầng.

### Bài học

- Tối ưu latency phải đo theo từng node và từng network boundary.
- Provider abstraction cần test isolation; môi trường bên ngoài không được làm unit test thay đổi kết quả.

## Tuần 5 — 31/08 đến 06/09

### Mục tiêu

- Chốt phiên bản bàn giao và giải quyết các điểm cuối về lifecycle tài liệu, truy vấn thời gian và citation viewer.

### Đã hoàn thành đến 31/08

- Quản lý version và soft archive xuyên Backend–Agent–Chroma.
- Overhaul giao diện review và cập nhật dependency Agent.
- Universal temporal query expansion cho ngày tháng/chứng từ.
- Coreference resolution cho các câu hỏi tiếp nối.
- Tinh chỉnh PDF highlighting và resize.

### Kiểm chứng ngày 01/09

- Backend Pytest: 152 passed.
- Agent/core: 589 passed, 44 skipped, 6 failed, 8 errors; phần live bị chặn network và còn hai lỗi isolation cấu hình LLM.
- Ruff còn findings; Frontend lint/typecheck/build đã pass, nhưng dependency audit còn 3 High và 2 Moderate vulnerabilities.
- Chi tiết: [`docs/TESTING.md`](docs/TESTING.md).

### Công việc chốt bàn giao

- [x] Đồng bộ README với source hiện tại.
- [x] Viết lại kiến trúc và sơ đồ.
- [x] Bổ sung đặc tả/thiết kế chuẩn.
- [x] Ghi tài liệu kiểm thử trung thực theo baseline.
- [x] Dựng lại weekly journal/worklog từ commit `develop`.
- [ ] Xử lý các quality gate còn mở và chạy lại live tests trong môi trường đủ dependency.

### Bài học

- Hồ sơ bàn giao phải gắn với commit cụ thể; không dùng metric hoặc trạng thái từ baseline cũ để mô tả code mới.
- Worklog có thể dựng từ Git để tăng tính kiểm chứng, nhưng commit count không đại diện cho năng suất.
