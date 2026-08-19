# Báo cáo trạng thái hệ thống HR Assistant — Post-MVP

Ngày cập nhật: 19/08/2026

## 1. Mục tiêu

Đánh giá trạng thái hiện tại của toàn bộ hệ thống HR Assistant sau khi nhóm hoàn thành MVP; bao gồm worker, migration, dữ liệu, retrieval, evaluation, backend, frontend và khả năng chạy tích hợp.

## 2. Các phần hệ thống đã hoàn thành

- Kiểm tra worker evaluation và vòng đời job giữa agent với backend.
- Kiểm tra hệ thống migration, schema và RLS; không còn migration trùng hoặc sai thứ tự.
- Nhập bộ test post-MVP gồm 64 case, 74 lượt hỏi và 10 hội thoại nhiều lượt.
- Kiểm tra đủ 13/13 tài liệu trong live index.
- Rà soát 45 lượt cần retrieval:
  - 27 lượt có bằng chứng rõ, được đưa vào benchmark dev.
  - 18 lượt không đủ điều kiện chấm và được loại có lý do rõ ràng: thiếu quy định, cần dữ liệu cá nhân, xung đột contract hoặc thiếu fixture.
- Tạo qrels dev và kiểm tra 36/36 chunk nhãn còn tồn tại trong live index.
- Sửa runner để giữ đầy đủ ngữ cảnh ở câu follow-up, tránh chỉ đánh giá câu cuối rời rạc.
- Lưu thứ hạng chunk trong báo cáo để có thể chẩn đoán retrieval miss mà không phải gọi API lại.
- Tạo runner đánh giá hành vi nhiều lượt, chấm riêng runtime state và boundary role mà không dùng LLM tự chấm nội dung.
- Sửa cách tính điểm: lỗi mạng hoặc lỗi xác thực API không bị tính thành câu trả lời sai.

## 3. Kết quả đạt được

### Retrieval production — Hybrid + Rerank

- Hit Rate@1: **74,1%**
- Hit Rate@3: **92,6%**
- Hit Rate@5: **96,3%**
- Hit Rate@10: **100%**
- Recall@10: **98,1%**
- MRR: **0,849**
- Document Hit Rate@3: **100%**

Kết quả dense dùng làm mốc so sánh có MRR **0,807**. Hybrid + rerank cải thiện thứ hạng các đoạn trả lời đúng, đặc biệt ở top đầu.

### Kiểm thử hệ thống

- Agent/core: **449 test pass**.
- Backend: **106 test pass**.
- Worker và migration: **39 test pass** ở nhóm kiểm thử liên quan.
- Frontend production build: **pass** sau khi đồng bộ dependency theo lockfile.

## 4. Phần chưa có kết quả cuối

Đánh giá hành vi end-to-end trên 64 case/74 lượt chưa hoàn tất vì FPT Gateway trả:

```text
401 Unauthorized — Invalid API Key
```

Cùng một `FPT_API_KEY` đã được dùng cho chat, embedding và rerank. Kiểm tra trực tiếp cả ba endpoint đều trả 401, vì vậy đây là vấn đề hiệu lực/quyền của key phía FPT, không phải lỗi logic agent.

Batch đã dừng sau 54 lượt lỗi. Các lượt này được ghi là **không đánh giá được**, không tính thành kết quả 0/54 và không dùng để kết luận chất lượng hệ thống.

## 5. Việc cần làm tiếp

1. Tạo hoặc gia hạn một FPT API key hợp lệ, có quyền dùng các model chat, embedding và rerank đang cấu hình.
2. Cập nhật `fpt_api_key` trong file `.env`; không lưu key thật trong `.env.example`.
3. Chạy lại toàn bộ 64 case/74 lượt bằng runner đã chuẩn bị.
4. Dùng kết quả đó để xác định các lỗi hành vi agent thực sự; chỉ sửa những lỗi có bằng chứng, không sửa theo các lượt lỗi API.
5. Nếu cần chấm độ đúng nội dung câu trả lời để làm báo cáo release, thực hiện blind human review hoặc cấu hình judge độc lập. Bộ hiện tại mới là benchmark dev một người rà soát, chưa phải release ground truth.

## 6. Các commit đã hoàn thành

- `98ea43f` — Curate bộ retrieval dev và qrels post-MVP.
- `a52dde4` — Ghi nhận benchmark retrieval và trace chẩn đoán.
- `58c8a03` — Thêm runner đánh giá hành vi nhiều lượt.
- `650d671` — Không tính lỗi API vào điểm hành vi.

## 7. Kết luận

Các phần code, worker, migration, bộ qrels và retrieval benchmark của hệ thống đã hoàn thành. Retrieval hiện đạt mức tốt trên benchmark dev hợp lệ. Công việc còn lại để có kết quả end-to-end cuối là cập nhật FPT API key hợp lệ và chạy lại 74 lượt hành vi.
