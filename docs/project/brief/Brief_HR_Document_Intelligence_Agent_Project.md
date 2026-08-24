# PROJECT BRIEF

**Tên đề tài:** AI agent Tóm tắt và trích xuất tri thức tài liệu nội bộ (Doc Intelligence Agent)  
**Mã dự án:** P-153  
**Đơn vị/Bối cảnh ứng dụng:** Kho tài liệu nội bộ VinBigData  

| **Tóm tắt điều hành**<br>Xây dựng hệ thống AI Agent thông minh dựa trên LangGraph và RAG phục vụ việc thu thập, tóm tắt, trích xuất thông tin có cấu trúc (quyết định, trách nhiệm, deadline) và trả lời truy vấn xuyên tài liệu nội bộ VinBigData có trích dẫn chính xác; tích hợp cơ chế Human-in-the-Loop (HITL) để chuyên viên/người dùng xác nhận thông tin trích xuất quan trọng, phân quyền theo phòng ban và kiểm soát chặt chẽ chi phí/token cho tài liệu dài. |
| --- |

---

# 1. Project Overview

**Doc Intelligence Agent** là trợ lý AI thông minh xử lý và khai thác tri thức từ kho tài liệu nội bộ (quy trình vận hành, biên bản cuộc họp, quyết định ban hành, quy chế doanh nghiệp). Thay vì nhân viên phải tự tìm kiếm và đọc thủ công hàng chục trang tài liệu phức tạp, hệ thống tự động:
1. Nạp và tóm tắt văn bản (hỗ trợ cả tài liệu số hóa PDF/Word và tài liệu scan qua OCR Document AI).
2. Bóc tách dữ liệu có cấu trúc theo schema được xác thực (quyết định, phân công trách nhiệm, deadline).
3. Cho phép hỏi đáp tự nhiên, tổng hợp thông tin xuyên nhiều tài liệu (cross-document synthesis) với 100% câu trả lời có dẫn nguồn minh bạch (citations).
4. Cung cấp giao diện Human-in-the-Loop để người dùng/quản trị viên tri thức kiểm tra, hiệu chỉnh và phê duyệt trước khi lưu trữ chính thức hoặc phục vụ ra quyết định.

---

# 2. Problem Statement (Thực trạng & Vấn đề)

- **📍 Thực trạng:** Kho tài liệu nội bộ (quy trình, biên bản họp, quyết định ban hành) của VinBigData phân tán, rời rạc ở nhiều định dạng và phiên bản. Nhân viên gặp nhiều trở ngại khi tìm kiếm, mất nhiều thời gian đọc hiểu các văn bản dài và dễ bỏ sót các quy định cốt lõi.
- **🎯 Vấn đề:** Cần một giải pháp AI Agent toàn diện có khả năng:
  - Tự động thu thập, phân tích và tóm lược nhanh tài liệu dài.
  - Trích xuất chuẩn xác các trường thông tin có cấu trúc (*Ai chịu trách nhiệm? Quyết định gì đã ban hành? Thời hạn/deadline khi nào?*).
  - Trả lời truy vấn đa tài liệu, giải quyết câu hỏi phức tạp liên quan đến nhiều phòng ban.
  - Đảm bảo người dùng/chuyên viên có thể xác nhận và kiểm chứng thông tin trích xuất quan trọng.

---

# 3. Core Constraints (Ràng buộc cốt lõi)

- **🔒 Human-in-the-Loop (HITL):** Bắt buộc có quy trình xác nhận bởi con người đối với các thông tin trích xuất quan trọng phục vụ ra quyết định chiến lược hoặc lưu trữ vào cơ sở dữ liệu chính thức.
- **🔒 Bảo mật & Phân quyền tài liệu (RBAC / Department ACL):** Phân quyền truy cập tài liệu nghiêm ngặt theo phòng ban (R&D, HR, Operations, Legal...). Người dùng chỉ được truy vấn và xem dữ liệu trong phạm vi được cấp phép.
- **🔒 Độ chính xác trích xuất & Bắt buộc dẫn nguồn (Grounding & Provenance):** Nghiêm cấm bịa đặt thông tin (zero hallucination). Mọi kết quả trích xuất và câu trả lời phải kèm citation (tên văn bản, điều/khoản, số trang).
- **🔒 Kiểm soát chi phí tài liệu dài (Token & Cost Management):** Cảnh báo khi vượt ngưỡng token; áp dụng phân đoạn thông minh (hierarchical chunking) và routing mô hình tối ưu chi phí.

---

# 4. Project Objectives

| **Mục tiêu** | **Kết quả hướng tới** |
| --- | --- |
| **O1. Tóm tắt & Trích xuất nhanh** | Rút ngắn 80% thời gian đọc và bóc tách thông tin từ các tài liệu dài và biên bản nội bộ. |
| **O2. Dữ liệu có cấu trúc chuẩn** | Trích xuất chính xác 3 trường thông tin cốt lõi (*Quyết định, Trách nhiệm, Deadline*) theo schema kiểm chứng. |
| **O3. Truy vấn xuyên tài liệu** | Trả lời chính xác các câu hỏi đòi hỏi đối chiếu giữa nhiều văn bản/quy trình với trích dẫn minh bạch. |
| **O4. Phê duyệt tin cậy (HITL)** | 100% dữ liệu trích xuất chính thức được chuyên viên review và xác nhận qua giao diện trực quan. |
| **O5. An toàn & Phân quyền** | Cô lập dữ liệu giữa các phòng ban, phát hiện mâu thuẫn/trùng lặp văn bản và cảnh báo chất lượng OCR. |

---

# 5. Target Users & Roles

| **Vai trò** | **Nhu cầu chính** | **Quyền hạn trong hệ thống** |
| --- | --- | --- |
| **Nhân viên (Employee)** | Tra cứu quy trình, quyết định, hỏi đáp chính sách liên quan đến công việc và phòng ban. | Đăng nhập; đặt câu hỏi; xem tóm tắt, câu trả lời, trích dẫn nguồn trong phạm vi phân quyền phòng ban. |
| **Quản trị tri thức (Knowledge Admin)** | Quản lý kho tài liệu, bóc tách tri thức, cấu hình pipeline và kiểm soát chất lượng dữ liệu. | Upload tài liệu (PDF, Word, scan); kích hoạt trích xuất; review/chỉnh sửa và phê duyệt HITL; quản lý quyền truy cập phòng ban. |

---

# 6. Technical Stack

- **AI Agent & Orchestration:** **LangGraph** (StateGraph workflow, multi-turn dialogue, conditional routing) + **LLM context dài** (FPT.AI / GLM-5.2 / DeepSeek).
- **RAG & Retrieval:** Hybrid Search (Dense Vector + BM25/Sparse) + Reranker (`bge-reranker-v2-m3`) + **Vector DB** (Chroma Cloud / Supabase pgvector).
- **Document Processing & OCR:** **OCR (Document AI)** cho tài liệu scan; thư viện bóc tách tài liệu số (`PyMuPDF`, `pdfplumber`, `python-docx`).
- **Structured Extraction:** Schema extraction có kiểm chứng (Pydantic models, JSON schema validation, retry loop).
- **Backend:** **FastAPI** (Python 3.11+), Uvicorn, SQLAlchemy/asyncpg.
- **Frontend:** **Next.js 15**, React 19, TypeScript, CSS Modules / Tailwind.
- **Database & Deployment:** **PostgreSQL** (Supabase), Deploy **Vercel** (Frontend) + **Render** (Backend API), Docker container.

---

# 7. Project Deliverables (Yêu cầu đầu ra)

## 7.1 Mức Cơ bản (MVP Deliverables)
1. **Web Deploy & Phân quyền 2 vai trò:** Đăng nhập phân định rõ giữa **Nhân viên** và **Quản trị tri thức**.
2. **Upload & Xử lý tài liệu:** Upload tài liệu nội bộ đa định dạng (PDF, DOCX, scan).
3. **Agent Tóm tắt & Trích xuất có cấu trúc:** Tự động tóm tắt nội dung và bóc tách các trường: *Quyết định*, *Trách nhiệm*, *Deadline*.
4. **Hỏi đáp có trích dẫn:** Trả lời truy vấn tự nhiên kèm trích dẫn nguồn có thể mở rộng xem ngữ cảnh gốc.

## 7.2 Mức Nâng cao (Advanced Deliverables)
1. **Tổng hợp xuyên nhiều tài liệu (Cross-document Synthesis):** Phân tích, so sánh và kết hợp thông tin từ nhiều biên bản/quy định độc lập.
2. **Phát hiện mâu thuẫn / trùng lặp (Conflict & Redundancy Detection):** Tự động rà soát và cảnh báo các điều khoản xung đột giữa văn bản cũ - mới hoặc giữa các phòng ban.
3. **Memory ngữ cảnh dự án:** Duy trì lịch sử và ngữ cảnh phiên làm việc để xử lý chuỗi câu hỏi phân tích chuyên sâu.
4. **Human-in-the-Loop (HITL) Review Flow:** Quy trình chuyên viên review, chỉnh sửa và bấm nút "Xác nhận lưu trữ" cho dữ liệu trích xuất.
5. **Phân quyền theo phòng ban:** Quản lý ACL theo phòng ban, lọc vector search theo metadata phòng ban.
6. **Cảnh báo độ tin cậy OCR & Giới hạn Token:** Cảnh báo khi tài liệu scan bị mờ/chất lượng OCR thấp và cơ chế giám sát ngân sách token.

---

# 8. Success Metrics

| **Chỉ số** | **Mục tiêu** | **Phương pháp đo** |
| --- | --- | --- |
| **Citation Coverage** | 100% câu trả lời nghiệp vụ có trích dẫn; từ chối khi không có nguồn. | Kiểm thử tự động trên bộ eval + logging. |
| **Structured Extraction Accuracy** | ≥ 90% các trường *Quyết định, Trách nhiệm, Deadline* trích xuất chuẩn xác. | Đối chiếu Ground Truth có kiểm chứng chuyên viên. |
| **Citation Correctness** | ≥ 88% trích dẫn hỗ trợ trực tiếp cho khẳng định trong câu trả lời. | Human review theo rubric đánh giá. |
| **Cross-doc Synthesis Recall** | ≥ 85% câu hỏi đa tài liệu truy xuất đủ các chunk nguồn liên quan trong top 5. | Benchmark multi-hop qrels. |
| **HITL Turnaround Time** | < 2 phút cho chuyên viên hoàn thành việc review và duyệt 1 văn bản trích xuất. | Usability testing trên giao diện Admin. |
| **Latency** | P95 ≤ 8 giây cho truy vấn thông thường; P95 ≤ 15 giây cho trích xuất sâu. | Telemetry & Application logs. |
