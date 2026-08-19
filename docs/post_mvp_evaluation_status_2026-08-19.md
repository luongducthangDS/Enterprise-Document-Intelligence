# Trạng thái evaluation sau MVP — 19/08/2026

## Kết luận

MVP đã hoàn thành. Công việc hiện tại là mở rộng khả năng và xây lại phép đo
phù hợp với corpus hiện hành, không phải hoàn thiện lại MVP.

Bộ test case nhóm cung cấp là đầu vào phù hợp cho dev benchmark v2:

- thực tế có 64 case, dù mô tả đầu file còn ghi 58;
- bao phủ đủ 13/13 tài liệu NexaTech;
- có 74 lượt hội thoại, gồm 10 case follow-up và 7 hàng chứa nhiều lượt;
- 45 lượt cần candidate/gold chunk để chấm retrieval;
- 26 case chỉ cần chấm boundary/safety ở cấp case;
- toàn bộ là dev set đã nhìn thấy, không được dùng làm held-out release.

## Đã hoàn thành

1. Chuyển Markdown thành JSON có cấu trúc, giữ nguyên câu hỏi, persona, lý do và
   kỳ vọng gốc.
2. Liên kết các hàng `(tiếp #...)` với case trước để có thể replay hội thoại.
3. Gắn kỳ vọng và track đánh giá cho từng lượt.
4. Đối chiếu live Chroma: đủ 13/13 source dự kiến, tổng 189 chunk.
5. Tách ba vấn đề cần người chốt:
   - `nxv2_037`: kỳ vọng trả lời thuần luật xung đột Type-C contract hiện tại;
   - `nxv2_049`: kỳ vọng điều kiện `ANSWER` hoặc `INSUFFICIENT_EVIDENCE`;
   - `nxv2_054`: cần fixture thật có hai nguồn mâu thuẫn.
6. Chuẩn bị công cụ pooling từ ba nguồn: dense toàn corpus, BM25 và dense giới
   hạn trong tài liệu dự kiến. Tool không dùng judge và không tự biến ứng viên
   thành qrel.

## Chưa thực hiện

Candidate pool chưa chạy vì cần xác nhận rõ cho phép gửi 45 câu hỏi dev mới tới
embedding API và Chroma. Sau khi có pool, người kiểm tra phải chấm từng ứng viên:

- 2: chứa câu trả lời;
- 1: chỉ bổ trợ;
- 0: không liên quan.

Chỉ sau bước phân xử này mới được tạo qrels và báo Recall/Hit Rate. Không dùng
model tự chấm rồi coi ngay là ground truth.

## Thứ tự tiếp theo

1. Xác nhận egress 45 câu hỏi dev để tạo candidate pool.
2. Nhóm chốt ba contract flag và chấm relevance ứng viên.
3. Sinh qrels v2 đã duyệt.
4. Chạy retrieval dev và sửa lỗi theo A/B từng câu.
5. Chạy agent end-to-end dev.
6. Khi chuẩn bị release phiên bản mở rộng, tạo held-out mới từ người viết độc
   lập và chỉ chạy một lần.

Hiện chưa có bằng chứng phải bổ sung tài liệu ngay: bộ test mới đã phủ đủ 13
source và live index có đủ cả 13. Chỉ thêm data nếu phân tích failure hoặc nhu
cầu sản phẩm chỉ ra một chủ đề thực tế chưa có căn cứ nội bộ.
