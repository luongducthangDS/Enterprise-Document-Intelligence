# Đánh giá Dự án P-153 HR RAG Chatbot (Góc nhìn Product Manager)

Dựa trên việc rà soát các tài liệu thiết kế (`plan_eval.md`, `ARCHITECTURE.md`), nhật ký công việc (`WORKLOG.md`), và cấu trúc mã nguồn hiện tại, dưới đây là nhận định về tình trạng dự án xét trên 3 khía cạnh: **Dữ liệu (Data)**, **RAG Pipeline**, và **Đánh giá (Evaluation)**.

---

## 1. Về mặt Dữ liệu (Data)

**Điểm sáng:**
- Đã quy hoạch được cấu trúc thư mục tiêu chuẩn (`raw`, `processed`, `chunks`, `metadata`, `rejected`).
- Xác định được phạm vi dữ liệu rõ ràng (giải quyết pain point HR nói chung, thu thập đủ văn bản luật và template quy chế nội bộ).

**Vấn đề & Rủi ro:**
- **Nghẽn cổ chai ở Ingestion & Data Generation:** Theo `WORKLOG.md`, extractor pipeline (`src/ingestion/`) chưa thực sự chạy ra dữ liệu cuối. Thư mục `data/` hiện chỉ có cấu trúc chứ chưa có files ở `processed` hay `chunks`. Việc tạo dữ liệu tổng hợp (synthetic data) cho các domain hẹp như WFH policy, training đang bị block do chờ API key của GLM-5.2.
- **Rủi ro Chunking với dữ liệu Pháp lý/HR:** Dữ liệu luật lao động, quy chế thường có tính tham chiếu chéo rất cao (VD: "Theo khoản 2 điều 4..."). Nếu chiến lược chunking không xử lý tốt metadata và context window, các chunk sẽ bị phân mảnh ý nghĩa, dẫn đến Retrieval tồi tệ dù Embedding model có tốt đến đâu.

**Khuyến nghị PM:**
- Lập tức unblock việc lấy API Key hoặc dùng tạm model khác (như GPT-4o-mini / Gemini 1.5 Flash qua API free/tier thấp) để sinh synthetic data. Không để team ngồi chờ.
- Phải có bước "Human-review" (Review bằng mắt người) ngẫu nhiên 50-100 chunks đầu tiên sau khi chạy Ingestion để đảm bảo text không bị cắt ngang câu chữ hoặc mất bối cảnh điều luật.

---

## 2. Về mặt RAG Pipeline (Kiến trúc & Luồng xử lý)

**Điểm sáng:**
- Luồng xử lý thiết kế theo Graph (LangGraph) rất bài bản, chia module rõ ràng. Phân loại intent ngay từ đầu (Router) giúp tối ưu hóa chi phí (không gọi RAG cho câu chào hỏi, chitchat).

**Vấn đề & Rủi ro:**
- **Over-engineering (Thiết kế quá mức cần thiết) cho giai đoạn MVP:** Pipeline đang có quá nhiều Node phải gọi LLM: `router → retrieve -> grade → rewrite → generate → hallucination_check → confidence`. Việc lạm dụng "Agentic" luồng dài khi cơ sở hạ tầng retrieval chưa vững là một rủi ro lớn.
- **Latency (Độ trễ) & Lỗi dây chuyền (Cascade Failure):** 
  - Mỗi node gọi LLM sẽ cộng thêm 1-3 giây. Tổng thời gian cho 1 câu trả lời có thể lên tới 10-15s, mang lại trải nghiệm UX rất tệ cho người dùng cuối.
  - Lỗi tích lũy: Hiện tại Router đang misfire 5/21 ca (nhận nhầm HR question thành Out of scope). Nếu Router sai, toàn bộ luồng sau vô nghĩa. Tương tự, nếu Grade lọc sai (bỏ sót chunk quan trọng của câu hỏi multi-chunk), Generate sẽ bị thiếu thông tin và Hallucination check sẽ lại cấm câu trả lời.

**Khuyến nghị PM:**
- **Cắt giảm luồng để tạo Baseline vững chắc:** Tạm thời vô hiệu hóa `rewrite`, `hallucination_check`, và `confidence` trong luồng mặc định. Đưa pipeline về dạng MVP: `Router -> Retrieve -> Generate`. 
- Chỉ bật lại các Node nâng cao khi metric Baseline cho thấy cần thiết (Ví dụ: bật `rewrite` nếu thấy Hit Rate quá thấp do query người dùng quá ngắn/ngữ cảnh mập mờ).

---

## 3. Về mặt Evaluation (Đánh giá & Đo lường)

**Điểm sáng:**
- Đã nhìn nhận ra đúng bản chất của bài toán đánh giá RAG: Document-level hit rate là không đủ, phải đánh giá ở mức Chunk-level và phải xử lý được "Multi-chunk coverage" (câu hỏi cần nhiều chunk để trả lời). `plan_eval.md` được viết cực kỳ sắc sảo về mặt tư duy.

**Vấn đề & Rủi ro:**
- **Lý thuyết đồ sộ nhưng thiếu Dữ liệu đánh giá (Ground Truth) cốt lõi:** Kế hoạch Eval rất hoành tráng (7 tầng), nhưng hành động quan trọng nhất là tạo file `retrieval_qrels.json` (dữ liệu đánh dấu chunk nào trả lời cho câu nào) lại đang nằm ở trạng thái "Cần làm". 
- **Ảo tưởng sức mạnh (False Sense of Security):** Tài liệu ghi nhận Document hit rate lên tới 93.3%, trong khi Chunk hit rate chỉ 75%. Điều này chứng tỏ Embedding model đang làm tốt việc tìm "đúng sách", nhưng kỹ thuật Chunking/Ranking đang thất bại trong việc tìm "đúng trang". Nếu không có QREL chunk-level ngay bây giờ, team kỹ thuật sẽ không biết phải tune chunk size, overlap hay chunking strategy như thế nào.

**Khuyến nghị PM:**
- **Dừng việc code thêm các logic RAG hay các script đánh giá (ROUGE, nDCG...).**
- Cử toàn bộ nhân sự tập trung làm **Data Labeling** ngay lập tức: Gắn nhãn thủ công (hoặc LLM-assisted) `relevant_chunk_ids` cho 60-100 câu in_scope. Đây là "mỏ vàng" để quyết định sự thành bại của hệ thống.
- Chấp nhận làm thủ công trước cho 1 tập nhỏ để unblock việc đánh giá Tầng 2 (Retrieval). Retrieval mà dưới 90% Recall@5 cho chunk-level thì phần Generation phía sau không có ý nghĩa gì.

---

## 4. Về sự vắng mặt của GraphRAG (Câu hỏi chiến lược)

**Tại sao một dự án HR/Pháp chế như thế này lại không (hoặc chưa) sử dụng GraphRAG?**

GraphRAG (Knowledge Graph RAG) đặc biệt mạnh mẽ trong các bài toán pháp lý/nhân sự nhờ khả năng mô hình hóa các mối quan hệ phức tạp (Ví dụ: "Hợp đồng thử việc" -> "Chấm dứt" -> "Báo trước 3 ngày" -> "Thẩm quyền phê duyệt: Trưởng phòng"). Tuy nhiên, dưới góc nhìn quản trị dự án, việc **chưa** đưa GraphRAG vào ngay lúc này là **hoàn toàn hợp lý** vì các lý do sau:

1. **Chưa có Baseline RAG chuẩn:** Dự án đang chật vật ở mức cơ bản nhất (vector search, semantic chunking) và còn chưa có bộ QRELs (Ground Truth) để đánh giá chunk-level. Áp dụng GraphRAG lúc này giống như "chưa học bò đã lo học chạy", sẽ tạo ra một mớ bùng nhùng (complexity overload) rất khó để debug lỗi sai nằm ở đâu.
2. **Chi phí và thời gian Ingestion (Xây đồ thị):** GraphRAG yêu cầu dùng LLM để trích xuất Entity (Thực thể) & Relationship (Mối quan hệ) cho toàn bộ kho tài liệu. Với ngân sách/token đang hạn hẹp (team thậm chí đang phải đợi API Key để sinh synthetic data), chi phí xử lý văn bản luật dài hàng ngàn trang bằng LLM là không khả thi cho một bản MVP.
3. **Vector Search vẫn giải quyết được 80% nhu cầu:** Rất nhiều câu hỏi thường gặp của HR (Ví dụ: "Công ty có hỗ trợ tiền ăn trưa không?", "Bao nhiêu ngày phép một năm?", "Nghỉ thai sản được hưởng bao nhiêu tháng lương?") chỉ cần Semantic Vector Search thông thường kết hợp tốt với Chunking là đủ trả lời chính xác.

**Khuyến nghị PM về GraphRAG:**
- Tạm thời gác GraphRAG sang một bên (Phase 2 hoặc Phase 3).
- Chỉ đưa GraphRAG vào roadmap khi hệ thống đã đạt Hit Rate > 90% với Vector RAG truyền thống, nhưng vẫn liên tục thất bại ở các câu hỏi yêu cầu **"Multi-hop reasoning"** (suy luận nhiều bước, nhiều nguồn. Ví dụ: "Quy trình từ lúc nhân sự level 3 nộp đơn nghỉ việc đến khi nhận trợ cấp thất nghiệp liên quan đến những phòng ban nào và vi phạm những điều khoản nào nếu công ty chậm trả lương?").

---

## Kết luận & Ưu tiên hành động (Action Items)

Dự án có tư duy thiết kế hệ thống tốt, tài liệu mạch lạc, nhưng đang bị kẹt giữa việc "thiết kế một hệ thống quá lý tưởng" và "thiếu nền tảng dữ liệu thực tế để validate".

**Top 3 việc cần làm trong 48h tới:**
1. **[Data/Eval]** Bỏ qua mọi việc khác, tập trung tạo xong file `eval/datasets/retrieval_qrels.json` cho ít nhất 50 câu hỏi HR lõi.
2. **[RAG]** Bypass (tắt tạm) các node `grade`, `rewrite`, `hallucination_check` để đo độ trễ (latency) và chất lượng sinh text của luồng `Router -> Retrieve -> Generate` thuần túy.
3. **[Ingestion]** Chạy thử pipeline ingestion trên 1 file luật (VD: Bộ Luật Lao Động), xuất ra `data/chunks/` và trực tiếp mở file json/csv ra đọc bằng mắt người để đánh giá chất lượng chunking. Tránh tình trạng "chưa có chunk nào mà đã code tính năng RAG".
