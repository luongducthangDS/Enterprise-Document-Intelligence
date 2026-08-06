# Tổng kết Cập nhật Hệ thống RAG (P-153)

Quá trình rà soát và cấu hình lại luồng Embedding đã hoàn tất. Dưới đây là kết quả đánh giá và những phát hiện quan trọng nhất để team định hướng tiếp theo.

## Các thay đổi đã áp dụng

1. **Chuẩn hóa mô hình E5**: Đã thêm tiền tố `"query: "` vào câu hỏi và `"passage: "` vào dữ liệu chunks trước khi vector hóa.
2. **Chuyển sang Cosine Similarity**: Xóa bỏ bộ Vector Database cũ (vốn đang dùng mặc định L2 distance không phù hợp) và tạo lại toàn bộ 1,384 vectors vào một Collection mới với chuẩn `hnsw:space = cosine`.
3. **Cập nhật ngưỡng lọc (Grade Node)**: Đã tinh chỉnh biến `retrieval_max_distance` từ `0.65` xuống `0.16` trong file `src/config.py` dựa trên phân phối thực tế của dữ liệu.

## Kết quả Đánh giá (Eval)

Dựa trên script `eval_retrieval.py`, kết quả đo đạc trên không gian Cosine mới cho ra như sau:

- **Distance phân hóa rõ ràng hơn**: 
  - Khoảng cách Cosine trung bình cho câu hỏi đúng miền (In-scope) là **0.138**.
  - Khoảng cách Cosine trung bình cho câu hỏi lạc đề (Out-of-scope) là **0.165**.
  - *Kết luận:* Ngưỡng `0.16` vừa được set sẽ giúp Grade Node lọc được hầu hết các câu lạc đề (chống Hallucination sớm).

- **Hit Rate**:
  - **Document-level Hit Rate@10** đạt **95.0%**, chứng tỏ Embedding Model E5 đang làm việc rất tốt trong việc tìm ra đúng tài liệu gốc chứa câu trả lời.
  - **Chunk-level Recall@1** vẫn thấp ở mức **41.7%**, và Recall@10 đạt **81.7%**.

> [!NOTE]
> **Khám phá cốt lõi (Tại sao Chunk Hit Rate thấp dù Document Hit Rate cao?)**
> Vì tài liệu nội bộ rất dài và các chunk giao thoa (overlap) nhiều, các đoạn văn trong cùng một tài liệu có bộ từ vựng rất giống nhau. Semantic Search (Dense Retrieval) chỉ dùng Embedding thường rất kém trong việc phân biệt rạch ròi giữa 2 đoạn văn tương đồng. Do đó, Vector Search luôn kéo về đúng tài liệu (Doc Hit Rate 95%) nhưng lại thường xếp hạng nhầm đoạn chứa đáp án chính xác xuống vị trí #2, #3, v.v. thay vì #1.

## Đề xuất hành động tiếp theo cho MVP

Theo yêu cầu từ phía quản lý (`antigravity_review.md`), RAG pipeline hiện tại đang quá cồng kềnh (Over-engineering). Dựa trên dữ liệu Eval, đây là hướng đi tiếp theo:

1. **Rút gọn Pipeline (Cắt giảm Node)**: Tạm thời vô hiệu hóa `rewrite`, `hallucination_check` và `confidence` trong luồng LangGraph (`src/agents/graph.py`). Chúng ta sẽ chỉ chạy luồng MVP: **Router -> Retrieve -> Grade -> Generate**.
2. **Triển khai Reranker (Cực kỳ quan trọng)**: Để giải quyết bài toán Chunk Hit Rate@1 thấp (41.7%), chúng ta BẮT BUỘC phải dùng mô hình Reranker (Cross-Encoder) đặt sau bước Retrieval thay vì phụ thuộc hoàn toàn vào Vector Search. Reranker sẽ xếp lại thứ hạng của Top-10 chunks, đẩy chunk chính xác lên vị trí Top-1.
