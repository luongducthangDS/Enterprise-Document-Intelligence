# PRODUCT REQUIREMENTS DOCUMENT (PRD)

> **PRD lịch sử.** Tài liệu này mô tả mục tiêu kỳ vọng, không phải danh sách tính năng đã hoàn tất; trong đó mô hình 2 role và một số flow nâng cao đã lệch code hiện tại. Baseline triển khai dùng [`../../SYSTEM_SPECIFICATION_AND_DESIGN.md`](../../SYSTEM_SPECIFICATION_AND_DESIGN.md) và [`../README.md`](../README.md).

**Tên sản phẩm:** AI agent Tóm tắt và trích xuất tri thức tài liệu nội bộ (Doc Intelligence Agent)  
**Mã dự án:** P-153  
**Bối cảnh triển khai:** Hệ thống quản trị tri thức và tài liệu nội bộ VinBigData  

---

# 1. Document Control

| Thuộc tính | Giá trị |
|---|---|
| **Product Owner** | Team AI20K-Build-Phase-Cohort-3 |
| **Reviewers** | Mentor / Đội ngũ Chuyên gia VinBigData |
| **Status** | Approved Specification |
| **Related Documents** | Project Brief v2.0; System Architecture Design; Pipeline & Evaluation Spec |

---

# 2. Product Vision & Nguyên tắc

### Tầm nhìn sản phẩm (Vision)
Xây dựng một **Doc Intelligence Agent** toàn diện, giải quyết triệt để vấn đề phân tán tài liệu tại VinBigData bằng cách tự động hóa quá trình thu thập, tóm tắt, trích xuất thông tin có cấu trúc (*Quyết định, Trách nhiệm, Deadline*) và hỗ trợ truy vấn tri thức xuyên tài liệu với trích dẫn có thể kiểm chứng, đồng thời tích hợp cơ chế con người xác nhận (HITL) và phân quyền bảo mật theo phòng ban.

### Nguyên tắc sản phẩm (Product Principles)
1. **Evidence-First & Strict Grounding:** Không bao giờ suy đoán ngoài nội dung văn bản gốc; mọi câu trả lời và trích xuất đều phải có bằng chứng dẫn nguồn (Citations/Lineage).
2. **Human-in-the-Loop as a Safeguard:** Thông tin trích xuất phục vụ ra quyết định hoặc lưu chính thức phải qua bước xác nhận của Quản trị viên/Chuyên viên.
3. **Department-Aware Security:** Tự động lọc phạm vi tìm kiếm theo phân quyền phòng ban của người dùng (RBAC).
4. **Transparent Quality & Cost:** Cảnh báo rõ ràng khi chất lượng OCR thấp, khi phát hiện xung đột điều khoản, và quản lý chặt chẽ ngân sách token cho tài liệu dài.

---

# 3. Thực trạng, Vấn đề & Mục tiêu

### 📍 Thực trạng
Kho tài liệu nội bộ của VinBigData gồm hàng trăm quy trình vận hành, biên bản họp, quyết định bổ nhiệm, quy chế nội bộ nằm rải rác ở nhiều định dạng (PDF, DOCX, bản scan). Nhân viên gặp khó khăn lớn khi tra cứu chéo và tốn rất nhiều thời gian đọc các tài liệu dài hàng chục trang.

### 🎯 Vấn đề & Mục tiêu
- Cung cấp khả năng tóm tắt nhanh và chính xác tài liệu dài.
- Tự động bóc tách cấu trúc dữ liệu hành động: *Quyết định ban hành*, *Đơn vị/Cá nhân chịu trách nhiệm*, *Hạn chót hoàn thành (Deadline)*.
- Hỗ trợ hỏi đáp tự nhiên xuyên tài liệu (Cross-document synthesis), đối chiếu mâu thuẫn giữa các văn bản.
- Cung cấp giao diện xác nhận (HITL) và phân quyền truy cập theo phòng ban.

### 🔒 Ràng buộc cốt lõi
- **HITL Verification:** Bắt buộc có xác nhận từ người dùng có thẩm quyền trước khi lưu trữ hoặc sử dụng chính thức dữ liệu trích xuất.
- **Bảo mật & Phân quyền (RBAC):** Nhân viên chỉ được tra cứu các tài liệu được phân quyền theo phòng ban.
- **Độ chính xác & Dẫn nguồn:** Bắt buộc 100% trích dẫn minh bạch (tên file, số trang, điều khoản).
- **Kiểm soát chi phí tài liệu dài:** Quản lý giới hạn token, tối ưu hóa chi phí xử lý văn bản lớn.

---

# 4. Target Personas & Phân quyền người dùng

| Persona | Vai trò | Mục tiêu chính | Pain Points cần giải quyết |
|---|---|---|---|
| **Nhân viên (Employee)** | Người dùng cuối các phòng ban | Tra cứu nhanh quy trình, hỏi đáp quy định nội bộ, tìm deadline và trách nhiệm liên quan đến công việc. | Không nhớ tên tài liệu; văn bản quá dài; không biết bản nào mới nhất; không biết phòng ban khác quy định ra sao. |
| **Quản trị tri thức (Knowledge Admin)** | Chuyên viên quản trị tài liệu / Ops / Ban lãnh đạo | Upload tài liệu mới; duyệt và xác nhận thông tin trích xuất (HITL); quản lý phân quyền kho tài liệu; theo dõi báo cáo chất lượng. | Mất nhiều giờ nhập liệu thủ công; khó kiểm soát xung đột giữa các quyết định cũ và mới; lo ngại rò rỉ tài liệu giữa các phòng ban. |

---

# 5. User Journeys cốt lõi

### 5.1 Upload tài liệu & Trích xuất có cấu trúc tự động
1. **Quản trị tri thức** tải lên tài liệu (PDF, DOCX, bản scan) và gán nhãn phòng ban (R&D, HR, Ops...).
2. Hệ thống kiểm tra chất lượng file; nếu là bản scan, kích hoạt module **OCR (Document AI)** và hiển thị chỉ số OCR Confidence Score (cảnh báo nếu < ngưỡng).
3. Agent phân tích và chạy **Schema Extraction** có kiểm chứng, bóc tách:
   - *Tóm tắt tổng quan văn bản*.
   - *Danh sách Quyết định (Decisions)*.
   - *Phòng ban / Người chịu trách nhiệm (Responsibilities)*.
   - *Thời hạn hoàn thành (Deadlines)*.
4. Dữ liệu trích xuất được đưa vào hàng đợi chờ duyệt (Pending HITL).

### 5.2 Quản trị viên duyệt và xác nhận (HITL Workflow)
1. **Quản trị tri thức** mở màn hình *Duyệt tri thức*.
2. Hệ thống hiển thị bản trích xuất song song với tài liệu gốc (kèm vị trí highlight trích dẫn).
3. Quản trị viên có thể chỉnh sửa trực tiếp các trường nếu cần và bấm **"Xác nhận & Lưu trữ chính thức"**.
4. Dữ liệu sau khi xác nhận được đồng bộ vào Vector DB và Relational DB để phục vụ toàn bộ nhân viên.

### 5.3 Hỏi đáp & Tổng hợp xuyên tài liệu (Cross-document QA)
1. **Nhân viên** đăng nhập, nhập câu hỏi tự nhiên (ví dụ: *"Quy trình nghiệm thu dự án AI gồm các bước nào và deadline nộp báo cáo cho phòng R&D là ngày nào?"*).
2. Hệ thống kiểm tra quyền hạn phòng ban của nhân viên (RBAC filter).
3. Agent thực hiện truy xuất đa tài liệu (Multi-hop Retrieval), tổng hợp câu trả lời từ cả quy trình vận hành và quyết định dự án liên quan.
4. Giao diện trả về câu trả lời kèm **Citations** chi tiết (có thể click để xem đoạn trích gốc).

### 5.4 Phát hiện mâu thuẫn & Cảnh báo
1. Khi có văn bản mới được nạp, agent tự động so sánh với các văn bản hiện có cùng chủ đề.
2. Nếu phát hiện quy định xung đột (ví dụ: thời hạn quy trình cũ là 5 ngày, quyết định mới là 3 ngày), hệ thống gắn nhãn **Cảnh báo mâu thuẫn (Conflict Warning)** và thông báo cho Quản trị viên xử lý.

---

# 6. Yêu cầu đầu ra (Deliverables)

### 🔹 6.1 Mức Cơ bản (MVP Deliverables)
- **Web Deploy & Phân quyền 2 vai trò:** Đăng nhập phân quyền rõ ràng giữa **Nhân viên** và **Quản trị tri thức**.
- **Upload & Xử lý tài liệu:** Upload tài liệu nội bộ (PDF, DOCX, scan).
- **Agent Tóm tắt & Trích xuất có cấu trúc:** Tự động tóm tắt và trích xuất các trường: *Quyết định*, *Trách nhiệm*, *Deadline*.
- **Hỏi đáp có trích dẫn:** Trả lời ngôn ngữ tự nhiên kèm citation (tên văn bản, trang, điều/khoản).

### 🚀 6.2 Mức Nâng cao (Advanced Deliverables)
- **Tổng hợp xuyên nhiều tài liệu (Cross-document Synthesis):** Khả năng suy luận đa chặng (multi-hop reasoning) trên nhiều văn bản khác nhau.
- **Phát hiện mâu thuẫn / trùng lặp (Conflict & Redundancy Detection):** Tự động đối chiếu và cảnh báo khi có sự xung đột nội dung giữa các quy định cũ - mới hoặc giữa các văn bản liên quan.
- **Project Context Memory:** Duy trì ngữ cảnh dự án / chuỗi hội thoại nhiều lượt liền mạch.
- **HITL duyệt thông tin trích xuất:** Giao diện phê duyệt, chỉnh sửa và xác nhận dữ liệu bóc tách.
- **Phân quyền theo phòng ban:** Cô lập dữ liệu và tìm kiếm theo phòng ban (Department-based Access Control).
- **Cảnh báo độ tin cậy OCR & Giới hạn Token:** Cảnh báo chất lượng scan thấp và quản lý ngân sách token xử lý tài liệu dài.

---

# 7. Functional Requirements (Yêu cầu chức năng)

| ID | Module / Tính năng | Mô tả chi tiết | Mức ưu tiên |
|---|---|---|---|
| **FR-01** | Authentication & RBAC | Đăng nhập hệ thống, phân định 2 vai trò chính: *Nhân viên* và *Quản trị tri thức*; quản lý quyền theo phòng ban. | **Must** |
| **FR-02** | Document Ingestion & OCR | Upload tài liệu PDF/DOCX; tích hợp **OCR Document AI** cho tài liệu scan, tính toán OCR Confidence Score. | **Must** |
| **FR-03** | Structured Extraction | Bóc tách có kiểm chứng các trường: *Tóm tắt*, *Quyết định*, *Trách nhiệm*, *Deadline* bằng schema validation (Pydantic). | **Must** |
| **FR-04** | Grounded QA & Citations | Hỏi đáp tự nhiên trên tài liệu được phân quyền, đính kèm trích dẫn chính xác (tên file, số trang, đoạn trích). | **Must** |
| **FR-05** | Refusal & Safety Check | Tự động từ chối trả lời an toàn khi không đủ bằng chứng (`INSUFFICIENT_EVIDENCE`) hoặc câu hỏi ngoài phạm vi. | **Must** |
| **FR-06** | HITL Review Interface | Giao diện cho Quản trị tri thức xem lại, sửa lỗi và bấm "Xác nhận" thông tin trích xuất trước khi lưu chính thức. | **Must** |
| **FR-07** | Cross-document Synthesis | Khả năng truy xuất và tổng hợp thông tin từ 2 hoặc nhiều văn bản khác nhau để trả lời câu hỏi phức hợp. | **Should** |
| **FR-08** | Conflict & Duplicate Detection | So khớp điều khoản mới với kho tri thức hiện có, cảnh báo khi phát hiện mâu thuẫn về deadline hoặc quy định. | **Should** |
| **FR-09** | Project Context Memory | Lưu trữ lịch sử hội thoại và ngữ cảnh dự án trong session để hỗ trợ các câu hỏi tiếp nối (follow-up questions). | **Should** |
| **FR-10** | Token & Cost Control | Quản lý token budget, cảnh báo chi phí và áp dụng tóm tắt phân tầng (hierarchical summary) cho tài liệu dài. | **Should** |
| **FR-11** | Department Access Filter | Lọc vector search và cơ sở dữ liệu tri thức theo `department_id` của tài khoản đăng nhập. | **Must** |

---

# 8. Non-functional Requirements (Yêu cầu phi chức năng)

| ID | Tiêu chí | Yêu cầu kỹ thuật |
|---|---|---|
| **NFR-01** | **Performance** | Thời gian phản hồi hỏi đáp P95 ≤ 8s; xử lý tóm tắt & trích xuất văn bản dài P95 ≤ 20s. |
| **NFR-02** | **Security & Privacy** | Mã hóa dữ liệu đường truyền (HTTPS/TLS) và lưu trữ; bảo vệ dữ liệu bí mật nội bộ theo phòng ban. |
| **NFR-03** | **Accuracy & Reliability** | Độ chính xác trích xuất trường dữ liệu ≥ 90%; tỷ lệ hallucination câu trả lời < 2%. |
| **NFR-04** | **Scalability** | Kiến trúc module hóa (FastAPI + LangGraph + PostgreSQL + Vector DB), dễ dàng mở rộng dung lượng kho tài liệu. |
| **NFR-05** | **Usability** | Giao diện Next.js hiện đại, tương tác mượt mà, hỗ trợ xem trước văn bản gốc và trích dẫn trực quan. |

---

# 9. Technical Architecture & Tech Stack

```
[ Next.js Frontend (Vercel) ] 
         │ (HTTP/REST + JWT Auth)
[ FastAPI Backend (Render) ]
   ├── [ LangGraph Multi-Agent Orchestrator ]
   │      ├── Document Processing & OCR Node (Document AI)
   │      ├── Schema Extraction & Verification Node (Pydantic)
   │      ├── Multi-hop Retrieval & Hybrid Search (Chroma Cloud / pgvector)
   │      ├── Cross-document Synthesis & Conflict Detection Node
   │      ├── Grounded Answer & Citation Mapping Node
   │      └── HITL Verification Bridge Node
   └── [ PostgreSQL / Supabase ] (Users, RBAC, Documents, Extracted Knowledge, HITL Audit)
```

- **LLM & Agent:** LLM context dài + **LangGraph**.
- **Search & Vector DB:** RAG Pipeline + **Vector DB** + Hybrid Search + Reranker (`bge-reranker-v2-m3`).
- **OCR:** **OCR (Document AI)** cho tài liệu scan.
- **Extraction:** **Schema extraction có kiểm chứng** (Pydantic / Instructor).
- **Backend & Database:** **FastAPI** + **PostgreSQL** (Supabase).
- **Frontend & Hosting:** **Next.js 15** (TypeScript) deployed on **Vercel**, Backend on **Render**, Docker.
