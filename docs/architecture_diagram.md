# Kiến Trúc Hệ Thống & Sơ Đồ Điều Phối (Architecture Diagram) — P-153

> **Source of Truth:** Mã nguồn trên nhánh `develop` là chuẩn mực hoạt động của hệ thống.

---

## 1. Sơ Đồ Hệ Thống Tổng Quan (System Overview)

Hệ thống được thiết kế theo kiến trúc microservices phân tách rõ ràng giữa **Client Portal (Next.js 15)**, **Backend Nghiệp Vụ & Phân Quyền (FastAPI Backend)**, **Agent Điều Phối Tri Thức (LangGraph Agent Service)**, **Worker Phân Tích & Bóc Tách Cấu Trúc (Document Analysis Worker)**, cùng hệ thống lưu trữ phân tầng (**Supabase PostgreSQL** & **Chroma Cloud**).

```mermaid
flowchart TB
    subgraph ClientLayer["Tầng Trình Diễn (Next.js 15 Web App / Vercel)"]
        FE_Emp["Employee Portal\n(Chat, Tra cứu, Xem trích dẫn)"]
        FE_Review["Document Review HITL UI\n(Phê duyệt trích xuất tri thức)"]
        FE_Admin["Knowledge Admin Portal\n(Quản lý tài liệu, Index, Tickets)"]
        FE_Warmup["Warmup Ping Service\n(Giữ ấm backend & agent)"]
    end

    subgraph BackendLayer["Tầng Nghiệp Vụ & API (FastAPI Backend / Render :8000)"]
        BE_Auth["Auth & RBAC Service\n(JWT, Rate Limiting, Dept Roles)"]
        BE_Chat["Chat Service\n(Async Polling, History Persistence)"]
        BE_DocSub["Document Submission Service\n(Upload, Review & HITL Verification)"]
        BE_Ticket["Ticket Service\n(Auto Routing theo phòng ban)"]
        BE_ACL["Department Access Control (ACL)\n(Fail-closed filter: Company / Department)"]
        BE_Warmup["Warmup API Service"]
    end

    subgraph WorkerLayer["Tầng Xử Lý Bất Đồng Bộ (Background Workers)"]
        Worker_Analysis["Document Analysis Worker\n(LLM Structured Extraction: Decisions, Responsibilities, Deadlines)"]
        Worker_Ingest["Ingestion & Index Worker\n(Extract, Clean, Chunk, Embed)"]
    end

    subgraph AgentLayer["Tầng Điều Phối AI Agent (LangGraph Agent Service / Render :8001)"]
        Agent_Router["Intent Router\n(Greeting, In-scope, Ambiguous, Out-of-scope, Pure Statutory)"]
        Agent_RAG["Hybrid Retrieval & Reranker\n(Dense + BM25 + bge-reranker-v2-m3)"]
        Agent_Guard["Safety Guardrails\n(Hallucination Check, Confidence, Escalation)"]
    end

    subgraph StorageLayer["Tầng Lưu Trữ & Tri Thức"]
        DB_Postgres[("Supabase PostgreSQL (0001–0012)\nUsers, Profiles, Conversations, Submissions, Extracted Facts, Tickets")]
        DB_Chroma[("Chroma Cloud Vector DB\nMulti-domain collections: HR, Accounting, Product, Tenant-scoped")]
    end

    subgraph ModelGateway["Cổng Mô Hình & Dịch Vụ AI (FPT.AI / Model Gateway)"]
        LLM_Gateway["LLM Generation\n(GLM-5.2 / DeepSeek-V4-Flash)"]
        Emb_Gateway["Embedding Service\n(multilingual-e5-large)"]
        Rerank_Gateway["Reranker Service\n(bge-reranker-v2-m3)"]
    end

    %% Client to Backend
    FE_Emp -->|"REST / JWT"| BE_Chat
    FE_Review -->|"REST / JWT"| BE_DocSub
    FE_Admin -->|"REST / JWT"| BE_DocSub
    FE_Admin -->|"REST / JWT"| BE_Ticket
    FE_Warmup -.->|"Health Ping"| BE_Warmup

    %% Backend internal
    BE_Auth --> BE_ACL
    BE_Chat --> BE_ACL
    BE_DocSub --> Worker_Analysis
    BE_DocSub --> Worker_Ingest

    %% Backend to Storage & Agent
    BE_Auth --> DB_Postgres
    BE_Chat --> DB_Postgres
    BE_DocSub --> DB_Postgres
    BE_Ticket --> DB_Postgres
    BE_Chat -->|"Internal REST + Service Token + Dept Scope"| Agent_Router

    %% Worker to Storage & Gateway
    Worker_Analysis --> LLM_Gateway
    Worker_Analysis --> DB_Postgres
    Worker_Ingest --> Emb_Gateway
    Worker_Ingest --> DB_Chroma

    %% Agent Flow
    Agent_Router --> Agent_RAG
    Agent_RAG --> Agent_Guard
    Agent_Guard -->|"AgentAnswer DTO"| BE_Chat

    %% Agent to Gateway & Chroma
    Agent_RAG --> DB_Chroma
    Agent_RAG --> Emb_Gateway
    Agent_RAG --> Rerank_Gateway
    Agent_Guard --> LLM_Gateway
```

---

## 2. Phân Định Trách Nhiệm Từng Thành Phần (Responsibilities)

| Thành phần | Vai trò & Trách nhiệm chính |
|---|---|
| **Next.js 15 Frontend** | Giao diện đăng nhập/đăng ký chọn phòng ban, Chat tương tác đa lượt, hiển thị Trích dẫn nguồn (Citations), Giao diện duyệt tài liệu HITL ([`DocumentReview.tsx`](file:///d:/AI%20Engineer/VIN%20AI/P-153/frontend/components/DocumentReview.tsx)), Quản lý Tickets, và giữ ấm dịch vụ ([`WarmupPing.tsx`](file:///d:/AI%20Engineer/VIN%20AI/P-153/frontend/components/WarmupPing.tsx)). |
| **FastAPI Backend** | Quản lý JWT & RBAC phân quyền phòng ban, điều phối Chat bất đồng bộ (REST Polling), tiếp nhận và lưu trữ bài nộp tài liệu ([`document_submissions.py`](file:///d:/AI%20Engineer/VIN%20AI/P-153/backend/app/api/v1/endpoints/document_submissions.py)), kiểm tra quyền truy cập ([`access_control.py`](file:///d:/AI%20Engineer/VIN%20AI/P-153/backend/app/services/access_control.py)), và tự động tạo Ticket khi Agent yêu cầu escalation. |
| **LangGraph Agent** | Điều phối luồng xử lý thông minh không lưu trạng thái (Stateless): Viết lại câu hỏi đa lượt (`condense`), Phân loại ý định (`router`), Tìm kiếm lai (`retrieve`), Đánh giá tài liệu (`grade`), Viết lại truy vấn (`rewrite`), Sinh câu trả lời có dẫn nguồn (`generate`), Kiểm tra ảo giác (`hallucination_check`), Tính điểm tin cậy (`confidence`), và Đóng gói kết quả hoặc Yêu cầu mở Ticket (`escalate_ticket`). |
| **Document Analysis Worker** | Tự động bóc tách các trường dữ liệu có cấu trúc từ tài liệu (*Quyết định*, *Trách nhiệm*, *Thời hạn*) bằng LLM có kiểm chứng schema Pydantic, hỗ trợ quy trình HITL trước khi chính thức nạp vào kho vector. |
| **PostgreSQL (Supabase)** | Quản trị dữ liệu quan hệ với 12 migrations liên tục (`0001`–`0012`): Bảng người dùng, thông tin cá nhân & phân quyền phòng ban, lịch sử hội thoại, bài nộp tài liệu & thông tin bóc tách cấu trúc, danh mục ticket và audit logs. |
| **Chroma Cloud Vector DB** | Lưu trữ các chunk văn bản và vector nhúng 1024 chiều theo từng collection chuyên biệt (`hr_documents`, `accounting`, `product`, `tenant_nexatech_knowledge`). |

---

## 3. Sơ Đồ Luồng AI Agent (LangGraph Workflow)

```mermaid
flowchart TD
    START((Bắt đầu)) --> CONDENSE{"Có lịch sử hội thoại?"}
    CONDENSE -->|Có| CONDENSE_NODE["condense:\nViết lại câu hỏi độc lập"] --> ROUTER{"router:\nPhân loại ý định"}
    CONDENSE -->|Không| ROUTER

    ROUTER -->|greeting| DIRECT["direct:\nChào hỏi thân thiện"] --> FINALIZE_RESP
    ROUTER -->|ambiguous| CLARIFY["clarify:\nHỏi lại thông tin cần làm rõ"] --> FINALIZE_RESP
    ROUTER -->|pure_statutory| STATUTORY["statutory:\nTừ chối tư vấn luật thuần túy"] --> FINALIZE_RESP
    ROUTER -->|out_of_scope / personal| ESCALATE_TICKET["escalate_ticket:\nTạo Ticket chuyển phòng ban"] --> FINALIZE_RESP

    ROUTER -->|in_scope (HR / Kế toán / SP)| RETRIEVE["retrieve:\nHybrid Search (Chroma + BM25)\nkèm Bộ lọc Phòng ban (ACL)"]
    RETRIEVE --> RERANK["rerank:\nbge-reranker-v2-m3\nTính điểm phù hợp"]
    RERANK --> GRADE{"grade:\nKiểm tra tài liệu có đủ thông tin?"}

    GRADE -->|Không đủ & chưa hết lượt| REWRITE["rewrite:\nViết lại từ khóa tìm kiếm"] --> RETRIEVE
    GRADE -->|Đủ thông tin HOẶC hết lượt retry| GENERATE["generate:\nSinh câu trả lời kèm Citation"]

    GENERATE --> ANSWERABLE{"Có trả lời được không?"}
    ANSWERABLE -->|Có| HALLUC_CHECK["hallucination_check:\nĐối chiếu câu trả lời với nguồn"]
    ANSWERABLE -->|Không| CONFIDENCE

    HALLUC_CHECK --> CONFIDENCE["confidence:\nTính điểm tin cậy tổng hợp"]
    CONFIDENCE --> CONF_CHECK{"Điểm tin cậy đạt ngưỡng?"}

    CONF_CHECK -->|Đạt (>= 0.7)| FINALIZE["finalize:\nĐóng gói AgentAnswer kèm nguồn"] --> FINALIZE_RESP
    CONF_CHECK -->|Thấp (< 0.7)| ESCALATE_TICKET

    FINALIZE_RESP["PII-Safe AgentAnswer DTO\n(Trả về cho Backend)"] --> END_STATE((Hoàn tất))
```

---

## 4. Sơ Đồ Quy Trình Phê Duyệt Trích Xuất Tri Thức (HITL Document Review Workflow)

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Quản trị viên / Chuyên viên
    participant FE as Next.js (DocumentReview UI)
    participant BE as FastAPI Backend
    participant Worker as Document Analysis Worker
    participant DB as PostgreSQL (Supabase)
    participant Agent as Ingestion & Indexer

    Admin->>FE: Tải lên tài liệu mới (PDF / DOCX)
    FE->>BE: POST /api/v1/document-submissions (File + Dept Scope)
    BE->>DB: Lưu file & tạo bản ghi submission (Trạng thái: PENDING_ANALYSIS)
    BE-->>FE: Trả về submission_id

    BE->>Worker: Kích hoạt phân tích cấu trúc bất đồng bộ
    Worker->>Worker: LLM trích xuất Quyết định, Trách nhiệm, Deadline
    Worker->>DB: Cập nhật extracted_facts & chuyển trạng thái: NEEDS_REVIEW

    Admin->>FE: Truy cập trang Document Review
    FE->>BE: GET /api/v1/document-submissions (Lọc trạng thái NEEDS_REVIEW)
    BE-->>FE: Danh sách tài liệu kèm các thông tin đã bóc tách

    Admin->>FE: Kiểm tra, chỉnh sửa quyết định/deadline nếu cần & bấm "Phê duyệt"
    FE->>BE: POST /api/v1/document-submissions/{id}/approve (Đính kèm dữ liệu đã chuẩn hóa)
    BE->>DB: Cập nhật trạng thái: APPROVED & Lưu thông tin chính thức
    BE->>Agent: Kích hoạt Ingestion & Embed vào Chroma Cloud
    Agent-->>BE: Hoàn tất index tri thức mới
    BE-->>FE: Phê duyệt thành công — Tri thức đã sẵn sàng phục vụ tra cứu
```
