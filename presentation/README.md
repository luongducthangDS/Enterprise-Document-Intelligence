# Tài Liệu Thuyết Trình Demo Day & Video Demo (Pitch Deck & Demo Guide) — P-153

> **Dự án:** AI Agent Tóm tắt và Trích xuất Tri thức Tài liệu Nội bộ Đa Phòng ban (Enterprise Doc Intelligence Agent)  
> **Team:** AI20K-Build-Phase-Cohort-3 (Project P-153)

---

## 📁 Danh Mục Tệp Trình Bày (Files)

- `pitch_deck.pptx` / `pitch_deck.pdf`: Slide thuyết trình chính thức cho Demo Day (10 slides chuẩn).
- `video_demo.mp4` / Đường dẫn video: Video quay màn hình giới thiệu và demo tính năng trực tiếp (tối đa 4–5 phút).

---

## 🎯 Cấu Trúc Slide Thuyết Trình (Pitch Deck 10 Slides)

| Slide # | Tiêu đề slide | Nội dung trọng tâm |
|:---:|---|---|
| **1** | **Title & Introduction** | • Tên dự án: **Enterprise Doc Intelligence Agent (P-153)**.<br>• Slogan: *Hệ thống Trợ lý Tri thức Doanh nghiệp Thông minh & Phê duyệt Trích xuất Tự động*.<br>• Tên team & Thông tin khóa học VinUni AI20K Build Phase. |
| **2** | **Problem Statement** | • Dữ liệu nội bộ rời rạc (PDF, DOCX, scan) tốn hàng trăm giờ đọc hiểu mỗi tháng.<br>• Rủi ro lộ lọt thông tin nhạy cảm khi thiếu phân quyền truy cập theo phòng ban.<br>• AI tạo sinh dễ bị ảo giác nếu thiếu dẫn nguồn và thiếu bước con người xác nhận (HITL). |
| **3** | **Solution & Value Proposition** | • Trợ lý AI tích hợp RAG lai (Hybrid Search + Reranker) đảm bảo 100% câu trả lời có trích dẫn nguồn.<br>• Phân quyền tri thức theo phòng ban (Department ACL) chuẩn bảo mật fail-closed.<br>• Quy trình phê duyệt có con người (Human-in-the-Loop) bóc tách Quyết định, Trách nhiệm, Deadline. |
| **4** | **Product Demo & User Flows** | • Demo 1: Nhân viên tra cứu chính sách/quy trình đa tài liệu với trích dẫn trực quan.<br>• Demo 2: Quản trị viên duyệt bài nộp tài liệu trên giao diện HITL Document Review.<br>• Demo 3: Hệ thống tự động tạo Ticket chuyển phòng ban khi gặp yêu cầu cá nhân. |
| **5** | **System Architecture** | • Kiến trúc microservices phân tầng: Next.js 15 ↔ FastAPI Backend ↔ LangGraph Agent Service ↔ Supabase Postgres & Chroma Cloud.<br>• Cơ chế giữ ấm Warmup Ping triệt tiêu khởi động lạnh trên Cloud. |
| **6** | **AI / RAG Technical Approach** | • StateGraph 12 nodes: Condense đa lượt → Intent Router → Hybrid Search (E5-large + BM25) → BGE Reranker v2 → Answer Generator → Hallucination Check → Confidence Gate. |
| **7** | **Security & Governance** | • Department ACL cô lập tri thức giữa các phòng ban (HR, Kế toán, Sản phẩm).<br>• Lọc Prompt Injection (`strip_injection`) & Che giấu dữ liệu PII (`redact_pii`).<br>• Database trigger chống tự nâng quyền tài khoản. |
| **8** | **Evaluation & Benchmark Evidence** | • Router Accuracy: 95.7% – 96.4%.<br>• Retrieval Recall@10: 92.8% (Dev) / 91.4% (Kế toán) / 90.0% (Sản phẩm).<br>• 46 ca kiểm thử E2E Live không mock; 100% pass sau Remediation. |
| **9** | **Challenges & Learnings** | • Xử lý lệch intent DTO & đồng bộ single-source-of-truth cho Vector DB Collections.<br>• Bài học: Thiết kế bảo mật fail-closed ngay từ tầng dữ liệu và tầm quan trọng của HITL. |
| **10** | **Team & Next Steps** | • Danh sách 4 thành viên (Product, AI/RAG, Backend, Frontend).<br>• Roadmap phát triển tiếp theo: Streaming transport, tích hợp OCR offline, mở rộng Enterprise Connectors. |

---

## 🎬 Kịch Bản Video Demo (Video Demo Script — 4 Phút)

### ⏱ Phút 0:00 – 0:30: Mở đầu & Nêu bài toán
- Giới thiệu ngắn gọn thành viên và bài toán doanh nghiệp: Khó khăn khi tìm kiếm quy trình, chính sách trong hàng ngàn trang tài liệu nội bộ và nguy cơ rò rỉ dữ liệu giữa các phòng ban.

### ⏱ Phút 0:30 – 1:45: Demo Luồng Tra Cứu & Trích Dẫn Đa Phòng Ban (Cross-Doc QA)
- **Kịch bản 1:** Đăng nhập với tài khoản Nhân viên Nhân sự → Hỏi câu hỏi chính sách lương thưởng/làm thêm giờ → AI trả lời chính xác, đính kèm Citation chỉ rõ tên văn bản và điều khoản.
- **Kịch bản 2 (Bảo mật ACL):** Thử hỏi về tài liệu tài chính mật của phòng Kế toán → Hệ thống tự động từ chối an toàn theo đúng chính sách phân quyền phòng ban (Fail-closed).

### ⏱ Phút 1:45 – 3:00: Demo Quy Trình Phê Duyệt Tri Thức HITL (Document Review)
- Quản trị viên tải lên văn bản mới (*Quy trình Báo cáo Tài chính Q3*).
- Worker AI tự động bóc tách các trường: *Quyết định ban hành*, *Trách nhiệm thực hiện*, *Thời hạn (Deadline)*.
- Quản trị viên mở giao diện `DocumentReview.tsx`, kiểm tra các trường dữ liệu, hiệu chỉnh ngày tháng và bấm **"Phê duyệt (Approve)"** → Hệ thống nạp ngay vào kho tri thức vector.

### ⏱ Phút 3:00 – 3:30: Demo Điều Hướng Ticket Tự Động (Escalation)
- Nhân viên hỏi: *"Kiểm tra giúp tôi bảng lương cá nhân tháng vừa rồi"*.
- AI phát hiện yêu cầu thông tin cá nhân → Tự động tạo Ticket hỗ trợ gửi thẳng về phòng Nhân sự kèm thông báo rõ ràng cho người dùng.

### ⏱ Phút 3:30 – 4:00: Tóm Tắt Giá Trị & Kết Thúc
- Tóm lược các điểm nổi bật: 100% có trích dẫn, Bảo mật phân quyền phòng ban, Tích hợp phê duyệt HITL, và Sẵn sàng triển khai cloud với Render Blueprint.

---

## ✅ Checklist Chuẩn Bị Cho Demo Day

- [ ] Đường dẫn Web App trực tiếp (Live URL trên Render / Vercel) đã được kiểm tra truy cập ổn định.
- [ ] Backend và Agent đã chạy Warmup Ping (không bị timeout khởi động lạnh).
- [ ] Video Demo (độ phân giải 1080p, âm thanh rõ ràng) đã upload lên YouTube / Google Drive.
- [ ] Slide Pitch Deck PDF đã nạp vào repo tại `presentation/` và sẵn sàng trình chiếu trong 10 phút.
- [ ] Đội ngũ đã phân vai trả lời câu hỏi phản biện kỹ thuật của Ban Giám Khảo (Kiến trúc LangGraph, Phân quyền ACL, Kiểm soát ảo giác).
