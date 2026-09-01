# PM/BA Onboarding Overview — HR Document Intelligence Agent (P-153)

> **Tài liệu lịch sử.** Metric, role và trạng thái tính năng bên dưới có thể đã cũ. Bắt đầu từ [`README.md`](README.md) và bộ tài liệu bàn giao chuẩn được liên kết tại đó.

> Tài liệu tổng hợp dành cho PM/BA mới join dự án, gộp từ toàn bộ tài liệu sẵn có trong repo (Brief, PRD, Architecture, RAG pipeline docs, reports, worklog...). Đây là bản **tổng hợp — không thay thế** các tài liệu gốc; mọi chi tiết sâu hơn nên tra lại nguồn được ghi kèm.
>
> Cập nhật lần cuối tổng hợp: 2026-08-15. Trạng thái dự án bên dưới phản ánh baseline gần nhất được ghi nhận trong log (06–13/8/2026); một số mục có thể đã thay đổi từ đó — xem mục 8 để biết chỗ cần hỏi lại team.

---

## 0. Tóm tắt nhanh (TL;DR)

- **Sản phẩm:** Trợ lý hỏi-đáp tài liệu HR dựa trên RAG (Retrieval-Augmented Generation) + LangGraph agent, trả lời có trích dẫn nguồn, biết từ chối khi thiếu bằng chứng, và chuyển người khi câu hỏi vượt phạm vi tự động hóa.
- **Không phải:** hệ thống payroll/chấm công, không thay thế quyết định nghiệp vụ của HR, không xử lý PII nhạy cảm, chưa phải bản production.
- **Bối cảnh:** dự án nằm trong chương trình đào tạo/thi đấu **AI20K Build Phase — Cohort 3**, có mốc "Demo Day".
- **Trạng thái hiện tại:** pipeline RAG + agent đã chạy end-to-end, pass rate baseline 75.7% (140 câu, đo trên tập đã dùng để tune — held-out set thật **chưa chạy**), latency p50 ~15–35s (mục tiêu <3–5s, **chưa đạt**), luồng chat chính FE↔BE↔Agent đã nối thật; ticket/escalation, ingestion job, và việc chọn 1 backend duy nhất (đang có 2 backend song song) vẫn còn dang dở.

---

## 1. Project Overview / Vision

### Vấn đề cần giải quyết
Tài liệu HR trong doanh nghiệp phân tán nhiều file/định dạng/phiên bản; nhân viên mất thời gian tìm quy định hoặc hỏi lại HR những câu lặp lại; tìm kiếm từ khóa truyền thống xử lý kém với câu hỏi tự nhiên, có điều kiện, hoặc hội thoại nối tiếp *(docs/project/brief/Brief_HR_Document_Intelligence_Agent_Project.md)*.

### Đối tượng người dùng (Personas)

| Persona | Bối cảnh | Mục tiêu | Pain point |
| --- | --- | --- | --- |
| Nhân viên | Cần biết chính sách/quy trình nhưng không nhớ tài liệu | Nhận câu trả lời nhanh, biết đọc nguồn nào | Nhiều file, thuật ngữ khó, không rõ bản nào còn hiệu lực |
| HR Specialist | Xử lý nhiều câu hỏi lặp lại, cần nhất quán | Tra cứu, kiểm chứng, chia sẻ căn cứ | Tốn thời gian, khó theo dõi phiên bản |
| Admin/Team | Chuẩn bị demo, duy trì dataset | Nạp tài liệu, đánh giá chất lượng, xử lý lỗi | Dữ liệu không đồng nhất, thiếu ground truth/log |

*(nguồn: docs/project/prd/PRD_HR_Document_Intelligence_Agent.md, mục 4)*

### Mục tiêu kinh doanh
Rút ngắn thời gian tra cứu, giảm câu hỏi FAQ lặp gửi HR, tăng khả năng kiểm chứng nhờ citation, tạo nền tảng nhân rộng sang Legal/Finance/Operations. Nguyên tắc sản phẩm cốt lõi: **Evidence first; citation by default; refuse safely; simple to verify; measurable quality** *(PRD mục 2; Brief dòng 105-110)*.

### Phạm vi (In-scope / Out-of-scope)

**In-scope (MVP):**
- Kho 30–50 tài liệu HR (PDF/DOCX/XLSX máy đọc được)
- Ingestion → chunk → embedding → index
- Tìm kiếm ngữ nghĩa/hybrid + trích dẫn nguồn (citation)
- Hội thoại nhiều lượt (multi-turn)
- Cơ chế từ chối an toàn khi thiếu bằng chứng / câu hỏi mập mờ
- Web demo, bộ test 100–150 câu

**Out-of-scope:**
- Payroll/chấm công giao dịch, ERP/SAP/HRM
- Thực thi workflow/email/phê duyệt tự động
- Dữ liệu PII nhạy cảm, OCR tài liệu scan kém
- Tích hợp production thật, tư vấn pháp lý hoặc quyết định nhân sự tự động

*(nguồn: Brief mục Scope; PRD mục 3 Goals/Non-goals)*

### Ranh giới tương tác (mức độ agent được phép tự động hóa)
Tài liệu `docs/project/hr_interaction_boundary_plan.md` định nghĩa 4 mức vai trò cho assistant:

| Mức | Ý nghĩa |
| --- | --- |
| `ANSWER` | Trả lời trực tiếp từ knowledge base |
| `GUIDE` | Hướng dẫn người dùng tự thao tác |
| `PREPARE_AND_HANDOFF` | Thu thập context tối thiểu rồi chuyển cho người xử lý |
| `HUMAN_FIRST` | Bắt buộc trao đổi với manager/HR trước, agent không tự xử lý |

Có ma trận 64 scenario ánh xạ intent → vai trò → dữ liệu cần thu → nơi handoff. **Nhóm không được tự động hóa:** quyết định thử việc, chấp nhận nghỉ việc, thay đổi hợp đồng, tranh chấp lương, KPI/promotion, khiếu nại/quấy rối/kỷ luật, ngoại lệ nghỉ phép/WFH có ảnh hưởng pháp lý, sức khỏe tinh thần/an toàn/visa/privacy — tất cả bắt buộc `HUMAN_FIRST`.

---

## 2. Requirements

### 2.1 Functional Requirements (tính năng chính)

| Tính năng | Mô tả ngắn |
| --- | --- |
| **Hỏi đáp tài liệu (RAG chat)** | Nhận câu hỏi + lịch sử tối đa 8 lượt gần nhất → router phân loại intent (greeting / hr_question / ambiguous / out_of_scope) → retrieve (dense + rerank) → grade → generate (bắt buộc trích `[Nguồn N]`) → hallucination check → confidence → escalate nếu cần. Trả về `response`, `citations`, `confidence_score`, `needs_clarification`. |
| **Đa lượt hội thoại** | Agent stateless — backend truyền `history`; node `condense_node` viết lại câu hỏi follow-up thành câu hỏi độc lập. |
| **Làm rõ câu hỏi mập mờ** | Khi câu hỏi thiếu ngữ cảnh, agent trả `needs_clarification=True` kèm câu hỏi gợi ý. |
| **Từ chối an toàn (refusal)** | 4 trạng thái chuẩn hóa: `INSUFFICIENT_EVIDENCE`, `OUT_OF_SCOPE`, `AMBIGUOUS`, `CONFLICTING_SOURCES`. |
| **Escalate / tạo ticket** | Khi confidence thấp hoặc ngoài phạm vi, agent tạo `TicketDraft`. **Lưu ý:** nếu response có `boundary`, hệ thống KHÔNG tạo ticket thật — chỉ hiển thị theo `boundary.runtime_action`; chỉ path legacy mới tạo ticket. |
| **Quản lý tài liệu & Ingestion** | Upload PDF/DOCX/XLSX → extract (pdfplumber, hoặc VLM Qwen2.5-VL cho scan) → clean → chunk hybrid → embed → index Chroma Cloud. |
| **Agent Worker (job admin)** | 3 loại job: `ingestion`, `index-rebuild`, `evaluation`, backend poll trạng thái qua `GET /api/v1/agent/jobs/{job_id}`. |
| **Evaluation pipeline** | 3 tầng: router eval, retrieval eval, agent end-to-end (LLM-judge dùng model khác họ với agent để tránh circular evaluation) + guardrail multi-turn pilot. |
| **Feedback & Monitoring** | Thumbs up/down gắn message; xem retrieval/latency (không log PII). |

Chi tiết user story (US-01 → US-08) và acceptance criteria (AC-01 → AC-10) xem `docs/project/prd/PRD_HR_Document_Intelligence_Agent.md` mục 6, 13.

### 2.2 Non-functional Requirements & ràng buộc kỹ thuật

| Hạng mục | Trạng thái / mục tiêu |
| --- | --- |
| **Guardrail AI** | 6-node graph cố định, không tool-calling tự do → hạn chế rủi ro tool misuse. Prompt injection: behavioral guard + `strip_injection()` cắt câu nghi injection khỏi RAG chunk. PII: regex redact email/SĐT/CCCD (mức MVP, chưa NER). |
| **Latency** | p50 tổng ~16.6s, p50 in-scope ~19–35s tùy điều kiện đo. Mục tiêu <3–5s — **chưa đạt**, cần redesign graph (song song hóa/streaming) mới cải thiện đáng kể. |
| **Test coverage** | 87% (167 test) — đạt mục tiêu >60%. Backend 70 passed, Agent/RAG 215 passed. |
| **RBAC** | Schema `Profile.access_level` đã định nghĩa nhưng **chưa enforce** trong code agent/API. |
| **Row-Level Security (RLS)** | Migration đã viết nhưng **chưa xác nhận đã apply** lên Supabase thật — migration `0003` chặn tự leo quyền `hr_admin` khi signup cần kiểm tra gấp. |
| **Rate limit** | Có mã lỗi chuẩn hóa `RATE_LIMITED (429)` nhưng cơ chế cụ thể còn "TBD". |
| **Audit log** | Mức MVP, in JSON ra stdout, cố tình không log query thô để tránh rò rỉ PII. |
| **Release gate đề xuất** (PRD mục 14) | Không nên demo là hệ thống đáng tin cậy nếu Citation correctness <85%, Answer correctness <80%, Recall@5 <85%. |

---

## 3. User Flow / User Journey

*(Chưa có wireframe/mockup trong repo — chỉ có mô tả luồng dạng text trong PRD và sơ đồ kiến trúc/agent-flow dạng Mermaid tại `docs/project/diagrams/`.)*

**Luồng 1 — Hỏi một câu hỏi mới**
1. Người dùng mở ứng dụng, nhập câu hỏi.
2. Hệ thống hiển thị trạng thái "đang tìm kiếm".
3. Hệ thống trả lời kèm citation, hoặc từ chối an toàn nếu không đủ bằng chứng.
4. Người dùng mở citation để kiểm tra đoạn nguồn và metadata (document, version, ngày hiệu lực).

**Luồng 2 — Hỏi tiếp nối theo ngữ cảnh**
5. Người dùng đặt câu hỏi follow-up (vd. "Còn nhân viên thử việc thì sao?").
6. Hệ thống diễn giải câu hỏi dựa trên lịch sử phiên (`condense_node`), nhưng vẫn truy xuất lại bằng chứng — không dựa mù quáng vào câu trả lời trước.
7. Câu trả lời mới có citation riêng.

**Luồng 3 — Không đủ dữ liệu**
8. Hệ thống phát hiện bằng chứng dưới ngưỡng hoặc câu hỏi ngoài phạm vi.
9. Hệ thống nói rõ không tìm thấy thông tin đủ tin cậy, không tự suy đoán.
10. Nếu phù hợp, đề nghị diễn đạt lại hoặc liên hệ HR (tùy `boundary.runtime_action`: NONE / LINK_ONLY / PREFILL_DRAFT).

**Sơ đồ kỹ thuật liên quan** (dạng Mermaid, xem trực tiếp trong repo):
- `docs/project/diagrams/agent_flow_diagram.mermaid` — luồng xử lý bên trong agent
- `docs/project/diagrams/system_overview_diagram.mermaid` — tổng quan hệ thống
- `docs/project/diagrams/deployment_diagram.mermaid` — deployment
- `docs/project/diagrams/workflow.mmd` — workflow tổng thể
- Ảnh render sẵn tại `docs/project/diagrams/images/*.png`

---

## 4. Data & Architecture Overview

### 4.1 Kiến trúc tổng quan
Agent RAG chạy trên **LangGraph**, phục vụ qua FastAPI endpoint nội bộ (`POST /api/v1/chat` / `/api/v1/agent/query`). Ingestion chạy offline (extract → clean → chunk → embed) nạp vào **Chroma Cloud**. Khi có câu hỏi: retrieve → rerank → sinh câu trả lời có trích dẫn → tự chấm confidence → tạo ticket/escalate khi cần. Backend (Supabase/FastAPI) lo auth, lưu hội thoại, quản lý ticket.

Kiến trúc 3 lớp: **Next.js FE → FastAPI BE (auth, RBAC, conversation, ticket, PostgreSQL) → FastAPI Agent/LangGraph (ChromaDB + FPT.AI gateway)** *(docs/project/integration/AGENT_BE_FE_INTEGRATION.md)*.

**Agent graph (12 node):**
```
condense → router → (direct | clarify | retrieve) → grade
  → (generate | rewrite → retrieve)
  → generate → hallucination_check → confidence → (finalize | escalate_ticket)
```
Agent **stateless** — lịch sử hội thoại do backend truyền vào mỗi lần gọi.

### 4.2 Công nghệ chính
- **LLM:** GLM-5.2
- **Embedding:** multilingual-e5-large (prefix `passage:` / `query:` chuẩn E5)
- **Reranker:** bge-reranker-v2-m3 — dùng điểm reranker (0–1) làm confidence thay vì cosine distance, vì phân phối in/out-of-scope chồng lấn quá nặng khi dùng cosine
- **Gateway:** FPT.AI Marketplace (OpenAI-compatible), dùng chung cho cả ingestion và agent
- **Vector store:** Chroma Cloud
- **Database:** Supabase Postgres

### 4.3 Data model (tóm tắt quan hệ chính)
`users`/`profiles` (1-1, có `manager_id` tự tham chiếu) → `conversations` (thuộc 1 profile) → `messages` (thuộc conversation, liên kết `chat_request_id`/`ticket_id`) → `chat_requests` (có `user_message_id`/`assistant_message_id`, `parent_chat_request_id` cho retry) → `tickets` (liên kết `requester_id`, `assignee_id`, `message_id`, `conversation_id`). Ngoài ra: `documents` (uploaded_by), `ingestion_jobs`, `index_jobs`, `evaluation_runs` *(docs/project/database/relationDB.md)*.

> Có đề xuất schema mở rộng (`docs/project/hr_physical_schema_and_knowledge_spec.md`) với bảng `hr_services`, `scenarios` (registry 64 scenario), `hr_cases`/`handoffs` — **đây là proposal, chưa migrate**. MVP-1 chỉ hỗ trợ action `ANSWER/GUIDE/PREFILL_DRAFT/LINK_ONLY`; các case nhạy cảm (ER/grievance) vẫn bắt buộc human-first vì chưa có ACL/audit/privacy đầy đủ.

### 4.4 Phạm vi knowledge base / dữ liệu
3 nhóm tài liệu: Chính sách/quy định (nội quy, nghỉ phép, OT, WFH, bảo hiểm...), Vòng đời nhân viên (tuyển dụng, onboarding, thử việc, nghỉ việc), Hướng dẫn hỗ trợ (FAQ, biểu mẫu). Metadata bắt buộc: `document_id`, `title`, `category`, `version`, `effective_date`, `status`.

**⚠️ Điểm nhạy cảm cần biết:** nhiều tài liệu trong dataset là **synthetic/template**, không phải chính sách thật của một doanh nghiệp cụ thể; một phần có tham chiếu từ tài liệu nội bộ của các tập đoàn lớn tại Việt Nam (VinFast/Vingroup) — `docs/knowledge_base_scope_for_pitch.md` khuyến nghị **không nêu tên thương hiệu cụ thể khi pitch**, dùng cách gọi trung tính như "internal policy reference document". README.md lại nêu thẳng tên các nguồn này — **hai tài liệu chưa đồng bộ, cần thống nhất cách trình bày trước khi làm slide/pitch cho khách hoặc ban giám khảo.** KB **không chứa** dữ liệu HRIS/payroll cá nhân → không trả lời được số dư phép/bảng lương cá nhân.

---

## 5. Roadmap / Timeline

### Delivery plan đề xuất trong PRD (6 tuần MVP — TBC)

| Tuần | Trọng tâm | Exit criteria |
| --- | --- | --- |
| 1 — Khởi động & thiết kế | Chốt data, use case, PRD, architecture, evaluation schema | Scope + sample dataset + baseline plan được review |
| 2 — Ingestion & baseline RAG | Parser, chunking, metadata, index, retrieval baseline | Hỏi đáp end-to-end trên subset |
| 3 — Phát triển vòng 1 | Backend/API, citation mapping, UI chat/source | Happy path chạy được |
| 4 — Phát triển vòng 2 | Multi-turn, refusal, version/conflict logic, logging | Feature-complete MVP |
| 5 — Đánh giá & sửa lỗi | Ground truth, metric run, tuning, UX test | Đạt release gate hoặc có gap report |
| 6 — Hoàn thiện & bàn giao | Deployment demo, docs, rehearsal, final report | Demo ổn định, artifacts đầy đủ |

### Timeline thực tế đã diễn ra (theo log)

| Thời gian | Sự kiện |
| --- | --- |
| 24–30/7 | Khởi tạo repo từ template AI20K, dựng git flow (`main`/`develop`/`feature/*`). Chưa chốt scope sản phẩm. |
| 31/7–07/8 | Chốt scope "HR Document Intelligence Agent" (không gắn 1 công ty cụ thể). Dựng ingestion, agent RAG (LangGraph), bộ eval 3 tầng. |
| 04–05/8 | Tổ chức lại dữ liệu nguồn (6 category), schema Supabase, demo UI đầu tiên, auth sign-in/up. |
| **06/8** | Ngày biến động nhất: một phiên sửa song song làm agent hỏng (reranker crash, escalate bị vô hiệu hóa âm thầm, thước eval bị phá) → audit khẩn, sửa dứt điểm cùng ngày: pass rate 63.5%→75.7%, router accuracy 88.6%→95.7%. |
| 07/8 | Dọn cấu trúc thư mục, merge PR #11 vào `develop`, bổ sung README/JOURNAL/WORKLOG còn thiếu. |
| 11/8 | Phát hiện lỗi chặn demo: FE kẹt trạng thái `CREATING`, Ticket API placeholder không auth, 1 test backend fail (`report_demo_1108.md`). |
| 12/8 | Ngày review nhiều nhất: đánh giá theo role (`PM_review.md`), góc nhìn kỹ thuật/data khi vào doanh nghiệp (`Review_128.md`), đề xuất kỹ thuật agent nâng cao (`Proposal_Agent_128.md`), siết contract BE↔Agent (`Contract_Boundary_128.md`), đo latency thật (`report_1208.md`). |
| 13/8 | `bug_1308.md`: verify lại các finding P0/P1, phân công owner theo team (chưa sửa code). |
| **15/8 (hôm nay)** | Chưa có log mới nhất trong `WORKLOG.md`/`JOURNAL.md` kể từ 07/8 — **cần hỏi team về tiến độ 2 tuần gần nhất**. |

**Số liệu baseline gần nhất (06/8):** Agent end-to-end 106/140 (75.7%), in-scope 71/100; Router accuracy 95.7%; Retrieval Recall@10 89.4%, Doc Hit@10 100%; latency p50 in-scope ~19–35s. **Lưu ý:** các số liệu này đo trên tập đã dùng để tune, held-out set (30+20 câu) **chưa từng được chạy** — nên coi đây là con số sơ bộ, chưa phải kết quả cuối.

---

## 6. Stakeholders & Roles

| Người/Vai trò | Đóng góp chính |
| --- | --- |
| Lương Đức Thắng | Phụ trách chính data/RAG pipeline/eval; viết phần lớn work log/report; review contract Agent↔Backend |
| Dương | Dựng demo UI luồng chat đầu tiên |
| hthanhson | Sign in/up, Conversation/Chat/Citation API, fix message-order |
| minhphu711 / minhphu | Soạn thảo PRD/brief |
| "son" (nhánh `feature/son`) | PR liên quan chat_service |
| **Ted** | Được nhắc trực tiếp khi cùng điều tra sự cố (vd. Supabase pooler) — có vẻ đóng vai trò PM/lead theo dõi quyết định |

Vai trò chuẩn (Product Owner, Developer, Code Reviewer, QA/Tester, Release Manager) được định nghĩa trong `GIT-FLOW.md` nhưng **chưa gắn tên cụ thể** ngoài các thành viên trên — nên xác nhận lại phân vai chính thức với team.

Bối cảnh tổ chức: dự án thuộc chương trình đào tạo/thi đấu **AI20K Build Phase — Cohort 3**, không có sponsor doanh nghiệp cụ thể; "Demo Day" là mốc quan trọng, nhiều báo cáo hướng tới chuẩn bị demo an toàn.

---

## 7. Risks & Open Issues

### Rủi ro chặn khả năng "bán vào doanh nghiệp" (ưu tiên cao nhất, theo `Review_128.md`)
- **Không có access control ở tầng retrieval** — RBAC dừng ở API, chunk không có metadata phòng ban/visibility → rủi ro rò rỉ thông tin nhạy cảm (vd. lương/thưởng cấp cao) nếu KB mở rộng dữ liệu thật.
- **Latency 15–35s** — chưa dùng được cho chat nội bộ thực tế (chuẩn kỳ vọng 3–5s).

### Rủi ro kỹ thuật/vận hành đang mở
| Vấn đề | Ghi chú |
| --- | --- |
| Ticket API placeholder | Không auth, không ghi ticket thật — agent báo đã escalate nhưng thực tế chưa xảy ra ("đang nói dối user" theo Review_128) |
| Ingestion/index/evaluation job | Dừng ở trạng thái `QUEUED`, chưa có worker thực thi thật |
| 2 backend song song | `src/api/` (Supabase Auth) vs `backend/` (JWT tự chế) — **chưa chốt hướng nào**, được nhắc lại xuyên suốt từ 06/8 đến 12/8, là rủi ro kiến trúc lớn nhất chưa giải quyết |
| Lệch contract BE↔Agent | `ai_agent_client.py` gọi `POST {url}/query` với body khác agent thật (`POST /api/v1/chat`); state `RETRIEVING` khai báo 5 nơi nhưng không code nào set; field `escalate_reason`/`target_department` là `str` lỏng thay vì `Literal` khớp Agent; 2 bộ test BE/Agent không dùng chung fixture nên có thể cùng xanh dù tích hợp đã gãy |
| Document upload bỏ nội dung | `document_service.py` đọc file rồi bỏ đi, không lưu bytes — cần fix trước khi bật ingestion job thật |
| Migration DB thiếu đồng bộ | 5 bảng (`users`, `chat_requests`, `ingestion_jobs`, `index_jobs`, `evaluation_runs`) có trong schema thật đang chạy nhưng thiếu trong migration → rủi ro deployment reproducibility (P1, có thể thành P0 nếu deploy fresh DB) |
| Chat job không durable | Process crash/restart giữa chừng có thể làm request kẹt `QUEUED` vĩnh viễn |
| History role mismatch | Backend dùng `user`/`assistant`, FE dùng `USER`/`ASSISTANT` — có thể render sai sau reload |
| RLS chưa xác nhận apply | Migration `0003` (chặn tự leo quyền `hr_admin`) — **cần xác nhận đã apply lên Supabase project thật** |
| Multi-chunk Recall không ổn định | Recall lệch mạnh dev/held-out (83.6% vs 55.0%, n=20 nhỏ); câu hỏi cần tổng hợp nhiều đoạn/tài liệu chưa ổn định, chưa có query decomposition |
| Eval mang tính circular một phần | Ground truth do LLM sinh + LLM chấm, 0 nhãn người xác nhận độc lập, 50 mẫu bất đồng chưa chấm tay |
| CI chưa gate eval | Chỉ chạy pytest, chưa chạy eval_agent/eval_retrieval trong CI |
| Dữ liệu chính sách công ty thật gần như trống | 16/28 tài liệu RAG-eligible là template công khai/synthetic; 2 tài liệu chính sách thật (VinFast, Vingroup) đều có caveat chưa xác minh hiệu lực — rủi ro chính xác pháp lý nếu demo cho khách mà không giải thích rõ |

### Quyết định còn treo (open decisions)
- Chốt dùng **1 backend duy nhất** (giữa `src/api/` và `backend/`)
- Bật/tắt `use_hybrid` retrieval
- Hạ ngưỡng `low_confidence_threshold` từ 0.5 → 0.2 (đã có số liệu đề xuất, chưa áp dụng)
- Xử lý nhãn dataset tự mâu thuẫn (case `qa_093` — Vingroup vừa được gán là "công ty mình" vừa bị gán nhãn competitor)

---

## 8. Điểm Ted nên xác nhận lại với team (mâu thuẫn giữa các tài liệu)

Trong lúc tổng hợp, phát hiện một số tài liệu **chưa đồng bộ** — nên hỏi lại team trước khi dùng để ra quyết định hoặc làm slide:

1. **Trạng thái Frontend:** `ARCHITECTURE.md` ghi nhận nhánh chính "chưa dựng FE", nhưng `docs/architecture_diagram.md` và `WORKLOG.md`/`AGENT_BE_FE_INTEGRATION.md` cho thấy Next.js FE đã nối API thật cho luồng chat chính. Cần hỏi team về trạng thái FE mới nhất tính đến 15/8.
2. **Tên thương hiệu trong dữ liệu (VinFast/Vingroup):** `docs/knowledge_base_scope_for_pitch.md` khuyến nghị tránh nêu tên cụ thể khi pitch, nhưng `README.md` nêu thẳng — cần thống nhất cách trình bày an toàn trước khi demo/pitch.
3. **Không có log cập nhật** trong `WORKLOG.md`/`JOURNAL.md` từ 07/8 đến nay (15/8) — 8 ngày không rõ tiến độ, cần hỏi trực tiếp trạng thái mới nhất của các hạng mục risk ở mục 7.
4. **Số liệu eval baseline (75.7% pass rate...)** đo trên tập đã dùng để tune — chưa chạy held-out set thật, nên tránh dùng con số này làm cam kết chính thức khi báo cáo ra ngoài.

---

## Nguồn tài liệu đã tổng hợp

- `docs/project/brief/Brief_HR_Document_Intelligence_Agent_Project.md`
- `docs/project/prd/PRD_HR_Document_Intelligence_Agent.md`
- `docs/project/hr_interaction_boundary_plan.md`
- `docs/project/hr_physical_schema_and_knowledge_spec.md`
- `ARCHITECTURE.md`, `README.md`, `docs/architecture_diagram.md`
- `docs/knowledge_base_scope_for_pitch.md`
- `docs/rag-pipeline/README.md`, `PIPELINE.md`, `AGENT_API.md`, `AGENT_WORKERS.md`, `AI_SAFETY_GUARDRAILS.md`, `folder_structure.md`
- `docs/project/API/APIdoc.md`, `apiBackend.md`
- `docs/project/database/relationDB.md`
- `docs/project/integration/AGENT_BE_FE_INTEGRATION.md`
- `JOURNAL.md`, `WORKLOG.md`, `frontend/WORKLOG.md`, `GIT-FLOW.md`
- `PM_review.md`, `Review_128.md`, `Proposal_Agent_128.md`, `Contract_Boundary_128.md`, `bug_1308.md`
- `docs/reports/project_review.md`, `ISSUES.md`, `EVAL_REVIEW.md`, `walkthrough.md`, `report_rag_review.md`, `report_eval_review.md`, `report_data_prep_pipeline.md`, `antigravity_review.md`, `glm_review.md`, `plan_eval.md`
- `report_1208.md`, `report_demo_1108.md`
