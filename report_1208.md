# Report review — 12/08/2026

Phạm vi review: đưa branch `feature/rag-agent-pipeline` lên ngang bằng `develop` mới nhất, sau đó review phần **RAG Agent pipeline** (`src/agents/**`, `src/api/routes.py`, `src/models/schemas.py`, `tests/test_agents/**`, `tests/test_api/test_agent_query.py`, `docs/rag-pipeline/**`). Các file thuộc `backend/` và `frontend/` **không được sửa** trong đợt này — chỉ đọc để đối chiếu, phát hiện gì thì ghi lại ở đây cho team liên quan tự quyết.

## 1. Đồng bộ branch với develop

- `origin/develop` đã merge PR #19 (chính là commit `0bfe3af` của branch này) — nội dung `develop` và branch hiện tại **giống hệt nhau về code**, chỉ khác 1 merge commit.
- Đã fast-forward `feature/rag-agent-pipeline` lên `915c482` (`git merge --ff-only origin/develop`) — không mất, không đổi bất kỳ dòng code nào, không cần rebase/resolve conflict.
- Toàn bộ ~2100 dòng thay đổi hiện có trên working tree (38 file) vẫn là **uncommitted**, giữ nguyên sau bước fast-forward.

## 2. Review phần RAG pipeline (phạm vi của tôi)

Đã đọc kỹ diff uncommitted của `router.py`, `retrieval.py`, `generation.py`, `service.py`, `routes.py` và test tương ứng. Chạy `pytest tests/test_agents tests/test_api` (Python 3.11, vì `backend/.venv` không có `langgraph`) và `ruff check`:

- **116/116 test pass, ruff sạch.** Không phát hiện bug logic trong phạm vi này.
- Các thay đổi chính đã review và khớp với `docs/rag-pipeline/AGENT_API.md`:
  - `generate_node`/`hallucination_check_node`: chỉ giữ lại các chunk thực sự được `[Nguồn N]` trích dẫn trong câu trả lời (`_cited_chunks`), thay vì trả về toàn bộ chunk đã retrieve — có fallback an toàn về toàn bộ context khi model không phát citation hợp lệ.
  - `router.py`: bypass LLM cho câu hỏi có từ khoá "hybrid/wfh/làm việc từ xa" rõ ràng (đỡ tốn 1 lượt LLM), chạy **sau** guard tên công ty đối thủ nên không phá logic out-of-scope hiện có.
  - `retrieval.py`: mở rộng query với từ đồng nghĩa tiếng Anh/Việt cho chủ đề Hybrid/WFH trước khi embed.
  - `service.py` (`astream_answer`): thêm timing per-stage vào audit log, chi tiết hoá các event `status` theo nhánh nhánh thực tế của graph (rewrite/retry, escalate...), và thêm event `done.answer` chứa `AgentAnswer` đầy đủ để service gọi (Backend) persist mà không phải tự ghép lại từ các event rời rạc.
  - `routes.py`: thêm endpoint `POST /agent/query/stream` (SSE), đúng theo contract đã tài liệu hoá.
- Không có file `src/` nào cần sửa thêm.

## 3. Vấn đề liên ngành — cần Backend + Frontend xử lý (không tự sửa)

### 3.1. [QUAN TRỌNG] Cảnh báo "nguồn không chính thức" sẽ biến mất khỏi UI sau khi merge

`finalize_node` (`src/agents/nodes/generation.py`) đã bỏ hẳn đoạn text tự nối "Nguồn tham khảo: ... [nguồn tham khảo/template, không phải chính sách công ty thật]" vào cuối câu trả lời — đây là thay đổi **đúng chủ đích**, chuyển sang dùng field `citations[].is_official_policy` có cấu trúc để client tự hiển thị (test `test_does_not_duplicate_structured_citations_in_answer` đã xác nhận).

Tuy nhiên khi đối chiếu Backend + Frontend hiện tại:

| Lớp | File | Có `is_official_policy` / `source_type`? |
|---|---|---|
| Agent contract | `src/models/schemas.py` (`Citation`) | ✅ cả hai |
| Backend response DTO cho danh sách message | `backend/app/schemas/conversations.py` (`CitationDTO`) | ❌ không có |
| Backend response DTO cho chi tiết citation | `backend/app/schemas/citations.py` (`CitationDetailDTO`) | ❌ không có |
| Frontend type | `frontend/lib/types.ts` (`CitationSummary`, `CitationDetail`) | ❌ không có |
| Frontend render | `frontend/components/ChatView.tsx` | ❌ không render ở đâu cả |

→ **Hệ quả nếu merge nguyên trạng**: user không còn thấy cảnh báo "đây là tài liệu tham khảo/template, không phải chính sách chính thức" ở bất kỳ đâu nữa — vừa mất tính năng an toàn đã có (trước đây nằm trong text), vừa chưa có tính năng thay thế (structured field chưa lộ ra tới FE). Đây là **regression về safety/UX**, đề nghị Backend + Frontend ưu tiên trước khi release chung với thay đổi này.

### 3.2. `source_type` mới dừng ở tầng lưu trữ Backend, chưa lộ ra API/FE

Field `source_type` (thêm ở commit `feat(agent): add source_type metadata to citation contract`) đã có ở:
- Agent contract (`src/models/schemas.py`)
- Backend DTO nội bộ (`backend/app/schemas/agent.py::AgentCitationDTO`)
- Backend DB model (`backend/app/domain/models/documents.py`, cột `source_type`)
- Backend adapter ghi DB (`backend/app/services/agent_answer_adapter.py`)

nhưng **chưa** có trong response DTO trả cho FE (`CitationDTO`, `CitationDetailDTO`) lẫn `frontend/lib/types.ts`/`api.ts`/`ChatView.tsx`. Cùng nhóm việc với mục 3.1 — nên làm chung một đợt.

### 3.3. Đã kiểm tra: không có xung đột logic giữa WIP hiện tại và fix của `feature/son`

`backend/app/services/chat_service.py` vừa bị 2 người đụng vào: fix `bef53e2` (message order, tác giả `hthanhson`, đã merge vào develop) và diff uncommitted hiện tại (211 dòng). Đã đối chiếu vị trí hunk: **không overlap** — fix message order nằm ở đầu file (`_get_recent_history`, dòng ~39-51 bản gốc), diff uncommitted bắt đầu từ dòng 66 trở đi. Không có rủi ro ghi đè lẫn nhau ở đây.

## 4. Đề xuất hành động

1. **Backend**: thêm `is_official_policy` + `source_type` vào `CitationDTO` (conversations.py) và `CitationDetailDTO` (citations.py), lấy từ cột đã có sẵn trong `CitationDB`.
2. **Frontend**: thêm 2 field trên vào `CitationSummary`/`CitationDetail` (types.ts) và event `citation` trong `api.ts`; render cảnh báo khi `is_official_policy === false` trong `ChatView.tsx` (badge/text cạnh citation) — đây chính là hành vi mà agent side đã chủ động nhường lại cho client.
3. Có thể gộp 3.1 + 3.2 thành 1 PR nhỏ phía BE+FE, không phụ thuộc gì thêm từ Agent.

## 5. Đăng nhập + màn hình loading (đã chạy thử local — chỉ verify, không sửa)

Đã tự chạy `next dev` (port riêng 3100, không đụng máy Ted) để kiểm tra vì Ted chưa test được. Kết quả:

- **`LoginView.tsx`**: diff uncommitted chỉ đổi text hiển thị (bỏ nhắc "Supabase", đổi thành "Backend") — không đổi logic. Code loading (`loading` state, nút submit disable + spinner `LoaderCircle`, `try/catch/finally` đảm bảo `setLoading(false)` chạy cả khi lỗi mạng) đã đúng, không có nguy cơ spinner treo vô hạn.
- **Màn hình loading ban đầu** (`HrKnowledgeApp.tsx`, `checkingSession`): đã confirm bằng SSR HTML thực tế — `<div class="app-loading">Đang khôi phục phiên...</div>` render đúng ngay từ server, style `.app-loading` (`next-app.css`) đã có (full-viewport, canh giữa). Logic: không có token trong localStorage → bỏ qua loading, vào thẳng `LoginView`; có token → gọi `api.me()`, lỗi thì `clearSession()` rồi vẫn tắt loading (`finally`) — không có đường nào bị kẹt ở màn hình loading.
- **`lib/api.ts`**: lỗi mạng (`fetch` throw) được bọc thành `ApiClientError("Không thể kết nối tới Backend.")`, LoginView hiển thị đúng vào ô lỗi — không bị nuốt lỗi âm thầm.
- **`next.config.ts`** (tách `distDir` dev/prod): không liên quan đăng nhập, chỉ tránh dev server ghi đè build production — không có rủi ro.
- Next.js dev server compile sạch, không lỗi console/log khi load trang `/`.

**Đã verify luồng đăng nhập thật (Backend → Supabase), cùng Ted điều tra trực tiếp trên máy:**

`backend/.env` không tồn tại trên máy — Backend fallback đọc `DATABASE_URL` từ `.env` ở gốc repo (`config.py`: `env_file=(".env", "../.env")`). Ban đầu gọi `POST /auth/register` bị `503 DATABASE_UNAVAILABLE` (timeout ~12s), nghi vấn lần lượt: project Supabase bị pause (**sai** — dashboard xác nhận Healthy, mọi subsystem xanh), firewall Windows chặn port 5432 (**sai** — `Test-NetConnection` TCP thành công), sai `DATABASE_URL`/password (**sai** — `psql` với password thật từ `.env` connect và `select 1` thành công ngay). Nguyên nhân thực tế nhiều khả năng nhất: `aws-0-ap-northeast-1.pooler.supabase.com` là load balancer với 3 IP đích, một target phía sau chập chờn khiến lần đầu asyncpg rơi trúng timeout trong khi `psql` rơi trúng IP tốt.

Sau khi xác nhận credential đúng, gọi lại trực tiếp cả 3 bước mà `LoginView.tsx` thực hiện, **qua Backend thật, không mock**:

| Bước | Kết quả | Thời gian |
|---|---|---|
| `POST /auth/register` | 201 | 8.7s (chậm, do pooler chập chờn) |
| `POST /auth/login` | 200, trả `access_token`/`refresh_token` | 2.1s |
| `GET /auth/me` (dùng token vừa nhận) | 200, đúng thông tin user | 2.0s |

→ Toàn bộ chuỗi `api.login()` → `api.me()` → `onAuthenticated()` mà `LoginView.tsx` gọi hoạt động đúng trên Backend thật. Code không có lỗi; độ trễ 2-9s ở lần gọi DB đầu tiên là do Supabase pooler (ngoài tầm kiểm soát của code trong repo này), không phải do cấu hình hay logic đăng nhập.

**Chưa verify được:**
- Không có browser tool (Playwright/chromium-cli) trong môi trường này nên **chưa click-test được** trực quan nút "Đăng nhập" đổi trạng thái spinner trên UI thật — chỉ verify qua code + SSR HTML + gọi thẳng API. Nếu Ted cần verify visual, có thể tự chạy `pnpm dev` rồi mở `http://localhost:3000`.
- Độ trễ 2-9s cho request DB đầu tiên nên được theo dõi thêm — nếu lặp lại thường xuyên, đề nghị Backend cân nhắc tăng `database_pool_size`/`database_connect_timeout_seconds` (hiện `pool_size=3`, `connect_timeout=4s` — khá chặt cho kết nối nguội tới pooler ở Tokyo) hoặc báo Supabase support về target chập chờn phía sau load balancer.

## 6. Đánh giá kiến trúc dài hạn — feedback cho Backend/Infra (không thuộc phạm vi Agent, chỉ tổng hợp lại để team quyết)

Tổng hợp từ một vòng review kiến trúc riêng (không phải review code lần này), đối chiếu lại với repo hiện tại. Điểm mạnh được ghi nhận: tách rõ Frontend/Backend/Agent, Agent stateless dễ scale ngang, Backend giữ hội thoại/ticket/citation đúng nghiệp vụ, SSE + polling fallback hợp lý, Chroma tách khỏi Postgres hợp lý cho RAG MVP.

### 6.1. [Ưu tiên cao] Auth/DB lệch thiết kế

Migration Supabase gốc theo `auth.users`, nhưng Backend hiện dùng `public.users` + `hashed_password` riêng (không qua Supabase Auth) — hai hướng thiết kế đang tồn tại song song, cần **chốt một hướng**:
- Dùng Backend JWT nội bộ (đang gần với code hiện tại hơn): cần migration chính thức cho `public.users`, bỏ hết wording/tài liệu nhắc "Supabase Auth" cho đúng thực tế.
- Hoặc chuyển hẳn sang Supabase Auth thật: Backend verify Supabase JWT, `profiles.id` tham chiếu `auth.users`.

Đây là rủi ro lớn nhất trong toàn hệ thống hiện tại — càng để lâu càng khó đổi hướng vì code/migration/docs sẽ lệch nhau nhiều hơn.

### 6.2. Backend đang ôm state chat request trong process

`chat_requests` + SSE + polling fallback là thiết kế hợp lý cho MVP, nhưng background task chạy trong process FastAPI hiện tại **mong manh khi scale**: restart server giữa chừng sẽ mất job đang xử lý, không có cơ chế phục hồi. Đề xuất bước sau: chuyển job xử lý chat sang queue/worker riêng (Redis + RQ/Celery/Arq). MVP hiện tại giữ nguyên được, chưa cần làm gấp.

### 6.3. Quan sát/health-check chưa đủ chi tiết

Health endpoint hiện chỉ trả `status: healthy` chung chung, không tách trạng thái từng dependency (DB, Agent service). Sự cố kiểu "không đăng nhập được" ở mục 5 phía trên (nguyên nhân là pooler Supabase chập chờn) mất nhiều bước loại trừ mới ra được — nếu có health check tách riêng theo dependency, sẽ chẩn đoán nhanh hơn nhiều lần sau.

### 6.4. Test coverage còn thiếu cho các edge case sau (liệt kê theo nhóm, không phải tất cả đều thuộc Agent)

**Thuộc phạm vi Backend/Infra:**
- SSE bị ngắt giữa chừng rồi client reload/poll lại — chưa có test e2e.
- Concurrency: 5-20 chat đồng thời, DB pool cạn, agent chậm, retry trùng — chưa có test tải.
- Idempotency: duplicate submit/retry có tạo trùng message/ticket không — có header nhưng chưa có test xác nhận.
- Background task (agent đang xử lý) khi process FastAPI restart/crash — chưa có test/cơ chế phục hồi.
- DB pooler timeout/flapping (đúng loại sự cố mục 5 vừa gặp) — mới bắt thành lỗi 503 đẹp, chưa có circuit breaker.

**Thuộc phạm vi Agent (Em có thể làm nếu Ted muốn):**
- Multi-source conflict: logic ưu tiên nguồn khi mâu thuẫn đã có sẵn trong prompt (`_GENERATE_SYSTEM`, `src/agents/nodes/generation.py:24`) nhưng **chưa có test riêng** verify hành vi này.
- Partial answer (hỏi 3 ý, chỉ tìm được 2 ý) — chưa có test cho trường hợp này.

### 6.5. Multi-hop / multi-query decomposition và latency 15-35s — đã là known limitation, không phải gap mới

Hai điểm này đã được chính `docs/rag-pipeline/AGENT_API.md` ghi nhận từ trước (mục "Giới hạn đã biết"), không phải phát hiện mới:
- Agent hiện chưa tự chia câu hỏi thành nhiều sub-query rồi retrieve nhiều lượt có kế hoạch — chỉ retrieve 1 lần cho toàn câu hỏi, tổng hợp từ multi-chunk/multi-source trong 1 lượt retrieve (hybrid BM25 + dense, rerank, nhiều `[Nguồn N]` trong context).
- Latency p50 15-35s là đặc điểm kiến trúc pipeline tuần tự (condense → router → retrieve → rerank → grade → generate → hallucination check → confidence), tách service không tự làm nhanh hơn — cần đo từng stage rồi mới quyết định tối ưu (bỏ/giảm hallucination check cho câu đơn giản, cache retrieval, parallel hoá một số bước).

Nếu team muốn nâng cấp thật, hướng đáng làm là thêm node `plan_retrieval` (condense → plan sub-questions → retrieve per sub-question → merge/dedupe/rerank → synthesize có xử lý mâu thuẫn nguồn → verify completeness) — đây là roadmap item cần lên plan riêng, không phải "fix" trong đợt review này.

---

## 7. Bóc tách latency và quyết định đánh đổi thinking mode (bổ sung tối 12/08)

Mục 6.5 ở trên nói latency "cần đo từng stage rồi mới quyết định tối ưu". Phần này là kết quả của việc đo đó, cùng một quyết định đánh đổi đã chốt.

### 7.1. Nguyên nhân thật: reasoning token, không phải context dài

Đo trực tiếp trên gateway FPT (`/chat/completions`), 12/08:

| Tác vụ | Model | Thời gian | Token sinh ra | Output hữu ích |
|---|---|---|---|---|
| `ping` → "OK" | GLM-5.2 | 5.538s | 173 | 2 ký tự |
| Router → "hr_question" | GLM-5.2 | 2,9–7,4s | 265–467 | 11 ký tự |
| Router → "hr_question" | DeepSeek-V4-Flash | 1,5–2,4s | 82–166 | 11 ký tự |
| Hallucination check → "PASS" | GLM-5.2 | 3,6–6,4s | 286–581 | 4 ký tự |
| Generate (context 1.670 token) | GLM-5.2 | 3,7s | 287 | 39 ký tự |

Cả hai model đều trả `reasoning_content`: GLM-5.2 viết ~1.000 ký tự suy luận rồi in ra đúng một chữ `hr_question`.

**Điểm quan trọng cho mọi tối ưu về sau: latency tỷ lệ với số token SINH RA, gần như không phụ thuộc độ dài context.** Generate với prompt 1.670 token chỉ mất 3,7s, trong khi `ping` với prompt 22 token mất 5,5s. Tức là nhồi thêm chunk vào prompt gần như miễn phí; để model "nghĩ" mới là chỗ đắt. Điều này bác bỏ giả thuyết trực giác "chậm vì context quá dài".

Hạ tầng retrieval gần như vô can: embedding 398ms + Chroma query 841ms + rerank 453ms ≈ **1,7s**, chỉ ~8% tổng thời gian. `chroma_collection_init` tốn 2,8s nhưng chỉ một lần cho mỗi tiến trình.

Hai yếu tố cộng thêm đã quan sát được: (a) retry hallucination biến 3 lệnh gọi LLM thành 5, cộng ~8s; (b) gateway dao động mạnh — cùng model, cùng prompt, cùng 271 token sinh ra: 2.946ms và 7.311ms ở hai lần gọi liên tiếp.

### 7.2. Gateway cho tắt reasoning — và đây là đòn lớn nhất

Thử 7 biến thể tham số, chỉ hai cách có tác dụng: `chat_template_kwargs: {"enable_thinking": false}` và `thinking: {"type": "disabled"}`. Lưu ý `reasoning_effort: none/low` **không có tác dụng** (gateway trả HTTP 200 nhưng vẫn sinh đủ 265–270 token reasoning) — đừng dùng nhầm tham số này.

| Tác vụ | Thinking ON | Thinking OFF |
|---|---|---|
| Router | 7,365s (467 token) | 0,817s (4 token) |
| Generate | 9,960s (940 token) | 2,516s (164 token) |
| Hallucination check | 6,351s (581 token) | 0,993s (2 token) |

### 7.3. ĐÁNH ĐỔI ĐÃ CHỐT: tắt thinking cho router, chấp nhận mất accuracy

A/B đầy đủ trên 140 câu `qa_eval_set` (`eval/results/router_thinking_ab.json`), cùng model DeepSeek-V4-Flash:

| | Accuracy | p50 | p95 |
|---|---|---|---|
| Thinking ON | **93,6%** (131/140) | 4,85 s | 12,48 s |
| Thinking OFF | **85,7%** (120/140) | **345ms** | 740ms |

**Ngưỡng lịch sử của router là ≥94% và phương án này không đạt.** Quyết định vẫn là bật tắt thinking, chấp nhận đánh đổi để lấy tốc độ. Ghi lại đầy đủ mặt trái để người sau xem lại có đủ dữ kiện:

- **11 câu đổi verdict thì cả 11 đều xấu đi**, không câu nào được sửa đúng — đây là suy giảm hệ thống, không phải nhiễu hai chiều.
- Lỗi rơi vào chỗ phiền người dùng nhất: `hr_question` bị đẩy nhầm sang `ambiguous` 9 câu (khi bật: 1) và sang `out_of_scope_or_personal` 7 câu (khi bật: 4). Ước tính **~11% câu hỏi HR hợp lệ sẽ bị hỏi lại một lượt thừa hoặc bị đẩy sang HRBP** thay vì được trả lời ngay. Ví dụ câu bị ảnh hưởng: *"Chủ nhật mình đi làm thêm thì tính lương bao nhiêu?"*, *"Tôi ốm đột xuất sáng nay mới biết, báo nghỉ kiểu gì?"*, *"Cuối năm mình còn 8 ngày phép chưa dùng thì xử lý thế nào?"*.
- **Không có câu `out_of_scope` nào lọt thành `hr_question`.** Đây là điểm khiến đánh đổi này chấp nhận được: rủi ro nằm ở phía *làm phiền người dùng*, không phải phía *trả lời liều những câu lẽ ra phải từ chối*. Lớp an toàn không bị chạm tới.
- Rollback chỉ cần đổi `thinking_router = True` trong `src/config.py`. Tín hiệu nên rollback: tỷ lệ hỏi lại/escalate trên production vượt mức chịu được.

### 7.4. Các node còn lại giữ nguyên thinking

Cờ được tách theo từng node (`thinking_router`, `thinking_condense`, `thinking_generation`, `thinking_hallucination`) vì mỗi node có bộ eval và ngưỡng riêng — không gộp thành một công tắc chung.

- **condense**: giữ bật. Quan sát end-to-end khi tắt: lượt multi-turn *"Vậy ngày thường thì sao?"* (đang trả lời đúng 150%, confidence 0,994) rơi xuống `answerable=False` → escalate low_confidence. Đây là hỏng chức năng, khác về chất so với việc giảm vài điểm accuracy.
- **generate**: giữ bật, chưa A/B (cần `eval_agent.py` với LLM judge).
- **hallucination_check**: giữ bật — **đã A/B và đây là chỗ KHÔNG đánh đổi được**, xem 7.6.

### 7.6. Vì sao hallucination_check không được tắt thinking, dù router thì được

Replay offline 60 câu `in_scope` (`eval/results/hallucination_thinking_ab.json`), cùng model GLM-5.2:

| | Agreement | p50 | Tỷ lệ PASS |
|---|---|---|---|
| Thinking ON (baseline) | — | 8,09 s | 43/60 |
| Thinking OFF | **78,3%** (47/60) | **609ms** (13x) | **50/60** |

Ngưỡng đồng thuận là ≥95% nên 78,3% đã trượt xa. Nhưng con số chỉ là một nửa lý do — nửa quan trọng hơn là **hướng sai**:

- **10/13 bất đồng là bản tắt thinking nói PASS trong khi bản bật nói FAIL.** Tỷ lệ PASS tăng từ 43/60 lên 50/60.
- Nghĩa là tắt thinking làm lớp chống bịa đặt **dễ dãi hơn** — nó bỏ lọt đúng thứ nó sinh ra để chặn.

Đây là khác biệt về bản chất so với router, và là lý do hai node cùng "nhanh hơn 13-14x" nhưng chỉ một cái được chấp nhận:

| | Router | Hallucination check |
|---|---|---|
| Hướng sai khi tắt thinking | Đẩy câu HR hợp lệ sang hỏi lại / HRBP | Cho qua câu trả lời đáng lẽ phải FAIL |
| Ai chịu hậu quả | Người dùng bị phiền thêm một lượt | Người dùng nhận thông tin sai mà không biết |
| Có phá lớp an toàn không | **Không** — 0 câu out_of_scope lọt thành hr_question | **Có** — đây chính là lớp an toàn |
| Kết luận | Đánh đổi được | Không đánh đổi |

Cùng loại lập luận đã từng dùng để bác `DeepSeek-V4-Flash` cho `hallucination_model` (76,7% đồng thuận): nhanh hơn bao nhiêu cũng không bù được một câu trả lời bịa lọt ra ngoài.

### 7.7. Kết quả cuối sau khi áp cấu hình

Đo lại đúng 7 case của bộ evidence thủ công, trước và sau:

| Case | Trước | Sau |
|---|---|---|
| MT-01 (OT tối đa) | 52,1s | **9,9s** |
| MT-02 (OT ngày lễ) | 49,2s | **16,4s** |
| MT-03 (dữ liệu cá nhân) | 1,9s | **0,5s** |
| MT-04 (câu mơ hồ) | 139,7s | **10,3s** |
| MT-05 (multi-turn) | 17,5s | **10,5s** |
| MT-06 (prompt injection) | 21,6s | **0,4s** |
| MT-07 (PII + in-scope) | 104,5s | **12,3s** |
| **Tổng** | **386,5s** | **60,3s** (6,4x) |

Hai case đổi hành vi, cần ghi nhận vì bộ evidence thủ công (`eval/MANUAL_EVAL_EVIDENCE.md`) mô tả hành vi cũ:

- **MT-04 — tốt lên.** Trước bị router xếp nhầm `out_of_scope_or_personal` → escalate thẳng. Giờ ra đúng `ambiguous` → hỏi lại: *"Bạn vui lòng cho biết 3 ngày nghỉ tuần sau là nghỉ phép năm, nghỉ ốm, hay nghỉ không lương?"*. Đúng kỳ vọng của `qa_076`. Lưu ý đây là quan sát một mẫu, không mâu thuẫn với kết quả A/B 140 câu (tắt thinking vẫn kém hơn tổng thể).
- **MT-06 — đổi theo hướng bảo thủ hơn.** Câu tấn công prompt injection trước đây được router xếp `hr_question`, agent trả lời bác bỏ có dẫn nguồn (con số 60 ngày là chế độ ốm đau BHXH, không phải phép năm). Giờ router xếp `out_of_scope_or_personal` → escalate sang HRBP. Vẫn an toàn (không bịa, không nhận vai), nhưng mất câu trả lời có giá trị giải thích. Đây là ví dụ cụ thể của cái giá đã chấp nhận ở 7.3.

### 7.5. Rút lại đề xuất song song hoá router + retrieve

Ban đầu đề xuất chạy song song hai node này vì router tốn 4–13s. Sau khi tắt thinking, router chỉ còn ~0,3s nên đề xuất mất giá trị, và số liệu mới cho thấy nó có hại:

- Nhánh out-of-scope hiện kết thúc trong ~0,5s vì router chặn trước khi gọi retrieval. Song song hoá sẽ kéo nhánh này lên ~1,7s — **chậm đi hơn 3x** ở đúng nhánh đang rẻ nhất.
- Gateway có rate limit thật: A/B bị HTTP 429 ngay ở concurrency 2 khi request nhanh lên. Gọi thêm embed+query+rerank vô ích cho ~29% request (out_of_scope + ambiguous) là tiêu quota vào việc sẽ bị vứt đi.

Không làm.

### 7.8. Escalation guard — lấy lại phần accuracy đã đánh đổi, gần như không tốn latency

Trade-off ở 7.3 có một điểm yếu: nó trả giá bằng đúng loại lỗi khó chịu nhất — chatbot **từ chối một câu nó hoàn toàn trả lời được**. Thay vì bật lại thinking cho 100% traffic để cứu vài phần trăm câu, cách rẻ hơn là chỉ verify các quyết định có hậu quả nặng.

**Thiết kế: fast router + escalation guard 3 tầng** (`src/agents/nodes/router.py::_guard_escalation`). Guard chỉ kích hoạt khi fast router trả `out_of_scope_or_personal` — nhánh mà phân loại sai đồng nghĩa với từ chối phục vụ:

| Tầng | Điều kiện | Hành động | Chi phí |
|---|---|---|---|
| 1 | Câu không có dấu hiệu hỏi quy định chung | escalate luôn | 0 LLM |
| 2 | Khớp heuristic personal rõ ràng (`"của tôi"` + lương/phép/đơn/hợp đồng) | escalate luôn | 0 LLM |
| 3 | Còn lại — vừa nhắc bản thân vừa hỏi quy định | verifier **có thinking**, prompt 2 lớp | +1 LLM |

Rule ở tầng 1–2 chỉ đóng vai circuit breaker (quyết định *có verify hay không*); việc đổi intent luôn do LLM verifier quyết. Định nghĩa dùng cho verifier không phải "câu có chứa thông tin cá nhân" mà **"không thể trả lời chính xác nếu không mở hồ sơ của chính người hỏi"** — đây là distinction quan trọng nhất, vì phần lớn câu hỏi HR đều có chữ "tôi/mình".

**Kết quả trên 140 câu** (`eval/results/router_escalation_guard_ab.json`), cost = confusion matrix có trọng số theo hậu quả (hr→personal = 5, personal→hr = 4, hr→ambiguous = 2, ...):

| Cấu hình | Accuracy | Tổng cost | Cost/query | HR bị từ chối oan | p50 |
|---|---|---|---|---|---|
| thinking ON | 93,6% | 33 | 0,24 | 4 (4,0%) | 4,85 s |
| fast router | 85,7% | 64 | 0,46 | 7 (7,0%) | 345ms |
| **fast + guard** | **87,1%** | **51** | **0,36** | **4 (4,0%)** | **378ms** |

Guard tốn thêm **33ms p50** (345 → 378) vì chỉ 4–6 câu trong 140 đi tới verifier, đúng như thiết kế 3 tầng nhắm tới.

**Phát hiện quan trọng khi bóc tách 4 câu còn lại: không câu nào là thiệt hại do tắt thinking.** Cả 4 đều bị `_mentions_competitor_company` chặn trước khi LLM kịp chạy, và baseline thinking ON sai đúng 4 câu đó:

- **qa_006** — *"Đi công tác nếu dùng taxi hoặc **Grab** di chuyển trong ngày thì được thanh toán tối đa bao nhiêu?"*: false positive, "Grab" ở đây là phương tiện đi lại chứ không phải công ty bị hỏi chính sách.
- **qa_051 / qa_052 / qa_053** — hỏi về Vingroup/VinFast, trong khi corpus **có** tài liệu của hai đơn vị này nên eval set gán `hr_question`. Rule lại chặn vì `internal_company_names` chỉ khai `v-nova`.

Tức là **thiệt hại thật của fast router ở nhánh escalate đã về 0**, và 4 câu còn lại là một vấn đề độc lập: mâu thuẫn giữa rule tên công ty và nội dung corpus. Cần Ted quyết hướng xử lý (nới rule theo ngữ cảnh, hay bổ sung Vingroup/VinFast vào `internal_company_names`) — chưa sửa vì nằm ngoài phạm vi đợt tối ưu latency này.

**Phần cost còn lại nằm ở nhánh khác:** `hr_question → ambiguous` 10 câu, chiếm 20/51 điểm cost. Guard cố tình không chạm nhánh này vì hậu quả nhẹ hơn hẳn (một lượt hỏi lại, cost 2, so với từ chối thẳng, cost 5). Nếu muốn hạ tiếp, đòn tiếp theo phải nhắm vào đây — nhưng nó thêm verifier cho một nhánh có volume lớn hơn nên cần cân nhắc lại ngân sách latency.

**Tổng kết đánh đổi sau khi có guard:** từ *"nhanh 14x, mất 7,9 điểm accuracy, nhánh từ chối oan tăng 4→7 câu"* thành *"nhanh gần 13x, mất 6,5 điểm accuracy, nhánh từ chối oan giữ nguyên 4 câu như bản chậm"*. Phần accuracy còn thiếu tập trung ở nhánh nhẹ nhất về hậu quả.

### 7.9. Ba sửa đổi sau review config

Review chỉ ra 3 chỗ cần chỉnh, làm theo đúng thứ tự: sửa rule Grab → chốt phạm vi sản phẩm → align nhãn eval → cập nhật comment.

**(1) `_mentions_competitor_company` xét quan hệ ngữ cảnh thay vì substring.**

Rule cũ chặn mọi câu có tên công ty xuất hiện, bất kể tên đó đóng vai trò gì. Khác biệt giữa câu competitor thật và câu bị chặn oan luôn nằm ở quan hệ ngữ pháp:

```
"Grab Việt Nam CÓ trả thưởng KPI..."   -> tên là chủ thể     -> chặn
"dùng taxi hoặc Grab di chuyển"        -> tên là phương tiện  -> không chặn
```

Rule mới chỉ chặn khi tên công ty đứng ở vị trí chủ thể/sở hữu (`của/tại/ở/nhân viên/công ty` + tên, hoặc tên + `có/trả/cấp/áp dụng/quy định...`), và ngữ cảnh phương tiện (`qua/trên/bằng/dùng/đặt/mua` + tên) được xét TRƯỚC vì nó thắng về ngữ nghĩa — trong *"mua hàng trên Shopee CÓ được hoàn thuế không"*, chữ "có" đứng ngay sau tên nhưng chủ thể vẫn là chính sách công ty mình.

Kiểm chứng trên toàn bộ 14 câu có tên công ty trong `qa_eval_set` (deterministic, không tốn API): **10/10 câu competitor thật vẫn bị chặn**, qa_006 được thả. Thêm 10 unit test trong `tests/test_agents/test_escalation.py`.

**(2) Chốt phạm vi sản phẩm cho Vingroup/VinFast → sửa nhãn eval, không nới rule.**

Đây không phải bug router mà là mâu thuẫn định nghĩa: `internal_company_names` khai persona demo là V-NOVA và comment ghi rõ *"tài liệu corporate policy thật chỉ là nguồn tham khảo"*, trong khi eval lại gán qa_051/052/053 (hỏi văn hoá/slogan/quy định VinFast) là `in_scope` vì corpus có tài liệu đó.

Quyết định: **giữ persona V-NOVA**, nên 3 câu này là câu hỏi về công ty khác. Nhãn được đổi `in_scope` → `competitor_comparison` với `expected_behavior: decline_politely` — khớp đúng hành vi mà `escalate_node` đang thực hiện (từ chối lịch sự, **không** tạo ticket, vì không có gì để HR của mình xử lý).

Toàn bộ trường cũ được giữ trong `label_history.previous_fields` kèm lý do và người quyết định, để nếu sau này đổi persona thì khôi phục được. Nguyên tắc áp dụng ở đây: **không nới classifier để pass eval khi chính nhãn eval mới là thứ lệch khỏi phạm vi sản phẩm** — cả bản thinking ON lẫn OFF đều chặn 3 câu này, tức hệ thống nhất quán, chỉ nhãn là sai.

**(3) Comment `router_model` tách bạch hai quyết định.**

Con số 95,7% là kết quả của phép **chọn model** (đo với thinking ON), không phải accuracy production. Comment mới ghi rõ cấu hình đang chạy đạt 85,7% raw / 87,1% sau guard, và tách:

```
chọn model            -> DeepSeek-V4-Flash
chiến lược reasoning  -> thinking OFF + escalation guard
```

**Kiến trúc sau tất cả các thay đổi, phân nhóm theo rủi ro thay vì tối ưu đồng đều:**

| Nhóm | Node | Thinking | Lý do |
|---|---|---|---|
| FAST PATH | router (+ rewrite) | **OFF** + escalation guard | Sai theo hướng phiền UX, cứu lại được bằng verifier có điều kiện |
| QUALITY-CRITICAL | condense | ON | Node quyết định; hỏng làm lệch toàn bộ retrieval phía sau |
| SAFETY-CRITICAL | hallucination check | ON | Tắt thì sai theo hướng FAIL→PASS, tức nới lỏng chính lớp an toàn |

`thinking_condense` vẫn giữ ON và **chưa** benchmark — mới có một quan sát multi-turn, chưa đủ để quyết. Đây là hạng mục đáng đo tiếp theo.

### 7.10. Kết quả cuối — tất cả chấm trên cùng một bộ nhãn

Sau khi sửa nhãn, mọi con số dưới đây được **tính lại từ `predicted_intent` đã lưu của từng lần chạy** và chấm theo bộ nhãn mới, để không rơi vào đúng lỗi mà `EVAL_SPEC.md` cấm: đổi cách đo giữa chừng rồi so hai con số không cùng hệ.

| Cấu hình | Accuracy | Cost | **HR bị từ chối oan** | p50 |
|---|---|---|---|---|
| thinking ON (baseline) | 95,7% | 18 | 1 | 4,85 s |
| fast router, chưa guard | 87,9% | 49 | 4 | 345ms |
| fast + guard | 89,3% | 36 | 1 | 378ms |
| **fast + guard + rule fix** | **92,1%** | **25** | **0** | **373ms** |

**Xác nhận chéo cho việc sửa nhãn.** Baseline thinking ON chấm theo nhãn mới ra đúng **95,7%** — trùng khít con số A/B chọn model lịch sử (134/140), vốn được đo từ trước khi 3 câu Vingroup/VinFast bị gán nhãn `in_scope`. Nói cách khác, sửa nhãn **khôi phục đúng hệ đo** chứ không phải nới lỏng để lấy điểm; con số 93,6% đo trước đó thấp hơn chính vì nhãn sai.

**Cấu hình đang chạy tốt hơn baseline ở đúng chỗ quan trọng nhất.** Nhánh nguy hiểm nhất — câu hỏi HR hợp lệ bị từ chối thẳng — về **0 câu**, trong khi baseline thinking ON vẫn còn 1, và vẫn nhanh **13x**. Phần chênh accuracy còn lại (92,1% vs 95,7%) nằm gọn trong `hr_question → ambiguous` (7 câu), tức hậu quả nhẹ nhất: người dùng bị hỏi lại một lượt rồi vẫn được trả lời.

Diễn giải theo ngôn ngữ đánh đổi ban đầu: từ *"nhanh 14x, mất 7,8 điểm accuracy, câu HR bị từ chối oan tăng 1→4"* thành ***"nhanh 13x, mất 3,6 điểm accuracy, câu HR bị từ chối oan giảm 1→0"***.

**Ba việc còn để ngỏ:**
1. `thinking_condense` chưa benchmark — mới có một quan sát multi-turn. Đây là hạng mục đo tiếp theo.
2. Nhánh `hr_question → ambiguous` (7 câu) là phần cost lớn nhất còn lại; muốn hạ thì phải thêm verifier cho nhánh có volume lớn hơn, cần cân lại ngân sách latency.
3. **CI gate `check_dataset_integrity.py` đang đỏ sẵn từ trước** (đã xác nhận bằng cách chạy trên bản gốc chưa sửa gì: ra đúng 5 lỗi y hệt). Nguyên nhân: chunk `amis_mau-thong-bao-quy-dinh-nghi-phep::0000` biến mất khỏi `data/chunks/`, kéo theo qa_117/118/119 và rq_040. Script gợi ý chạy `remap_qrels.py` — chưa chạy vì đó là đụng vào qrels, cần Ted xác nhận.

### 7.11. Chốt cấu hình router — SLO, telemetry, và known inefficiency

**Router optimization coi như DONE cho sprint này.** Không kéo tiếp 92,1% lên 95,7% bằng cách thêm complexity, vì hai chỉ số quan trọng nhất đã đạt: 0 câu HR bị từ chối oan và p50 373 ms.

**Latency đầy đủ** (riêng router node, n = 140):

| Cấu hình | p50 | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| thinking ON | 4,77 s | 9,45 s | 11,54 s | 12,48 s | 22,44 s | 29,73 s |
| fast router | 344 ms | 394 ms | 499 ms | 743 ms | 2,66 s | 3,00 s |
| **fast + guard + rule fix** | **372 ms** | **456 ms** | **738 ms** | **1,32 s** | **5,57 s** | **8,13 s** |

Đuôi p99 cao hơn fast router trần là **có chủ đích**, không phải regression — bóc tách theo việc câu có đi qua verifier hay không:

| Nhóm | n | p50 | p75 | p95 | max |
|---|---|---|---|---|---|
| Không qua verifier | **135 (96,4%)** | 371 ms | 450 ms | 856 ms | 2,78 s |
| Có qua verifier | **5 (3,6%)** | 5,30 s | 5,75 s | — | 8,13 s |

Nói cách khác: 96,4% traffic không trả "thuế thinking", và **p95 của cấu hình đang chạy (1,32 s) vẫn thấp hơn p50 của bản thinking ON (4,77 s)**. Với n = 140 thì p99 chỉ là câu chậm thứ 1–2, độ tin cậy thấp — không tối ưu theo p99 ở giai đoạn này.

**Acceptance criteria (Router SLO)** — cấu hình hiện tại đạt cả 5 trên bộ eval này:

| Tiêu chí | Ngưỡng | Hiện tại |
|---|---|---|
| Không regression lỗi high-cost so với thinking ON | — | cost 25 vs 18, không có lỗi cost-5 nào |
| False HR escalation ≤ baseline | ≤ 1 | **0** |
| Verifier trigger rate | < 5% | **3,6%** (5/140) |
| Router p50 | < 500 ms | **372 ms** |
| Router p95 | < 1,5 s | **1,32 s** |

**Telemetry verifier** (`AgentState.verifier_*`, ghi vào audit log mỗi request): `verifier_called`, `verifier_changed_route`, `verifier_latency_ms`. Hai metric tính trực tiếp từ log:

```
verifier_trigger_rate = #verifier_called      / #request
verifier_useful_rate  = #verifier_changed_route / #verifier_called
```

`useful_rate` là metric quyết định cho bước sau. Hiện tại verifier chạy 5 lần và sửa được route ở nhóm câu vừa-cá-nhân-vừa-hỏi-policy → ROI tốt. Nếu production trượt về kiểu "100 lần gọi, 5 lần sửa route, 95 lần xác nhận điều đã rõ" thì **lúc đó** mới đáng thêm tầng pre-filter. Trường telemetry chỉ xuất hiện khi fast router định escalate, để mẫu số của `trigger_rate` không bị pha loãng.

**Known verifier inefficiency (không sửa ngay).** Câu *"Làm thế nào để fix lỗi NullReferenceException trong code C#?"* lọt tới verifier vì cụm "làm thế nào" khớp policy signal, tốn ~5,7 s rồi vẫn escalate. Đây là lãng phí có thật nhưng chỉ 1/140 câu (0,7%): thêm heuristic "phi-HR" chỉ để cứu ngần đó traffic sẽ tạo một nhánh logic mới có thể sinh false negative — ROI chưa rõ. Ghi nhận thành *known inefficiency*, không phải bug. Nếu sau này sửa thì làm generic (tín hiệu technical/programming intent deterministic), **không** blacklist theo từ khoá và **không** thêm một classifier LLM nữa — làm vậy là phá chính mục tiêu latency.

Trường hợp này đã được cố định bằng test (`test_verifier_can_confirm_escalation`) để không ai vô tình "sửa" nó mà không cân nhắc đánh đổi.

---

## 8. P0 — Dataset integrity: điều tra chunk mất (CI gate đã xanh)

### 8.1. Kết quả điều tra: không phải data regression, cũng không phải "qrels stale thông thường"

Truy theo đúng chuỗi *source document → chunk content → vì sao ID biến mất*:

| Bước kiểm tra | Kết quả |
|---|---|
| Source document còn trong `data/raw`, `data/processed`? | **Không** |
| Có trong `document_registry.csv` (28 tài liệu)? | **Không** |
| Nội dung evidence còn ở chunk ID khác trong corpus? | **Không** — grep 3 cụm khoá đều 0 kết quả |
| Vì sao biến mất? | **Có chủ đích**, ghi trong `logs/CLAUDE-archive-2026-08.md` |

Nguyên văn log ngày 06/08:

> `amis_mau-thong-bao-quy-dinh-nghi-phep.docx` (tải ở nhóm B) thực ra là file **RỖNG** (toàn `………` để điền)... Đã sinh thêm `07_chinh-sach-nghi-phep.md` để thay thế làm nguồn thật cho category `leave_policies`.

Tức tài liệu bị loại **đúng** — nó là mẫu chưa điền, không phải chính sách. Nhưng bộ eval sinh trước đó vẫn giữ các câu hỏi lấy evidence từ chính những dòng trống ấy. `evidence_spans` của rq_040 là bằng chứng trực tiếp:

```
"– Thủ tục xin nghỉ phép:\n…………………………………………………………………\n
 – Sau khi quay trở lại làm việc, nhân viên phải …………………………………..……"
```

Đây là lý do **không chạy `remap_qrels.py`**: không có evidence thật nào để map tới, nên tool sẽ gán chunk gần nhất theo embedding và benchmark sẽ chấm agent dựa trên nguồn không phải nguồn gốc của câu hỏi — đúng cái bẫy "sửa benchmark để thích nghi với vấn đề".

### 8.2. Xử lý khác nhau cho hai nhóm, vì tình trạng của chúng khác nhau

Điểm này chỉ lộ ra khi mở qrel của từng câu:

| Câu | Qrel | Xử lý |
|---|---|---|
| qa_117, qa_118, qa_119 | **Chỉ 1 chunk duy nhất** = chunk đã mất | **Retire** — không còn evidence nào |
| rq_040 | **7 chunk**, chunk mất chỉ là 1 và có score = 1 | **Giữ câu**, chỉ gỡ entry stale |

`rq_040` sau khi gỡ vẫn còn **6 chunk có nhãn, trong đó 3 chunk score = 2** (từ `07_chinh-sach-nghi-phep` — chính tài liệu thay thế — và `leanh_mau-noi-quy-lao-dong`). Câu hỏi *"thủ tục xin nghỉ phép..."* vẫn trả lời được bằng corpus hiện tại, nên retire nó là loại oan một query held-out còn dùng tốt.

Ba câu retired được giữ nguyên trong file kèm `retired: true`, `retired_at`, `retired_reason` để truy vết, và bị loại khỏi phép tính metric ở `eval_router.py`, `eval_agent.py`, `check_dataset_integrity.py`.

**CI gate hiện xanh:**

```
retrieval_benchmark: 97 query, 96 qrel
qa_eval_set.json: 137 câu
qa_heldout_set.json: 30 câu
✅ Bộ eval nhất quán với chunk hiện tại
```

### 8.3. Số liệu router tính lại trên mẫu số mới (137 câu)

Ba câu retired đều thuộc `in_scope`, nên mẫu số nhóm `hr_question` giảm 97 → 94. Chênh lệch không đáng kể, nhưng ghi lại để mọi con số về sau truy được về đúng một định nghĩa:

| Cấu hình | n | Accuracy | Cost | HR bị từ chối oan | p50 |
|---|---|---|---|---|---|
| thinking ON | 137 | 95,6% | 18 | 1 | 5,00 s |
| fast router | 137 | 87,6% | 49 | 4 | 343 ms |
| **fast + guard + rule fix** | 137 | **92,0%** | **25** | **0** | **373 ms** |

Kết luận không đổi so với mục 7.10; SLO ở 7.11 vẫn đạt cả 5 tiêu chí.

---

## 9. P1 — Benchmark `thinking_condense` (quyết định: GIỮ BẬT)

Spec chốt trước khi chạy: [`eval/CONDENSE_EVAL_SPEC.md`](../eval/CONDENSE_EVAL_SPEC.md). Bộ 16 case, 4 nhóm × 4 (`eval/datasets/condense_multiturn_set.json`), kết quả đầy đủ ở `eval/results/condense_thinking_ab.json`.

### 9.1. Kết quả

| Metric | thinking ON | thinking OFF | |
|---|---|---|---|
| Answer correct | 15/16 | 15/16 | hoà |
| Retrieval hit | 16/16 | 16/16 | hoà |
| Wrong escalation (critical) | 1 | 1 | hoà |
| Unnecessary clarification | 0 | 0 | hoà |
| `reference_loss` | 0 | 0 | hoà |
| `reference_misresolution` | 0 | 0 | hoà |
| `topic_contamination` | 0 | 0 | hoà |
| Condense p50 | 1,93 s | **588 ms** | OFF nhanh 3,3x |
| E2E p50 | 17,91 s | 13,42 s | OFF nhanh 25% |
| E2E mean | 19,41 s | **21,05 s** | **OFF chậm hơn** |

**Không có condense regression nào.** Hai case duy nhất ON/OFF khác kết quả đều là nhiễu tầng sinh, và mỗi bên thua một case:

- **cd_002** (ellipsis): `retrieved_ids` **giống hệt nhau**, nhưng nhánh ON phát sentinel `[KHÔNG_ĐỦ_THÔNG_TIN]` (`answerable=False`) rồi escalate, trong khi OFF trả lời đúng "60 ngày". Rewrite hai bên chỉ khác đúng một từ ("với" / "đối với").
- **cd_008** (pronoun_reference): 7 chunk đầu **giống hệt, cùng thứ tự**; nhánh OFF trượt hallucination check nên confidence bị cap 0,1 rồi escalate. Rewrite hai bên khác một từ ("vùng I" / "tháng vùng I").

Nhóm control `topic_switch` sạch ở cả hai nhánh: rewrite không kéo chủ đề cũ sang câu mới, không có hiện tượng over-connect.

### 9.2. Một khiếm khuyết trong chính tiêu chí đo, đã sửa

Bản đầu phân loại `generation_variance` bằng cách so **toàn bộ** `retrieved_ids`. Với cd_008, hai nhánh ra cùng 7 chunk đầu theo đúng thứ tự nhưng một nhánh kèm thêm 1 chunk đuôi score thấp — đủ để `==` trả `False`, và case bị xếp nhầm vào "condense gây regression". Tức là đổ cho condense một lỗi thực ra sinh ở tầng generate/hallucination.

Đã sửa sang so **top-5 chunk đầu** (`TOP_K_EVIDENCE`), và tính lại từ dữ liệu đã lưu — không chạy lại API. Sau khi sửa: **0 case là condense regression thật**.

### 9.3. Đối chiếu acceptance criteria (chốt trước khi chạy)

| # | Tiêu chí | Ngưỡng | Kết quả | |
|---|---|---|---|---|
| 1 | Answer correctness không giảm > 1–2 điểm | | 15/16 → 15/16 | ✅ |
| 2 | Wrong escalation không tăng tuyệt đối (critical) | | 1 → 1 | ✅ |
| 3 | Retrieval hit không regression | | 16/16 → 16/16 | ✅ |
| 4 | **E2E** cải thiện đủ lớn, không chỉ riêng node | | chỉ **8/16** case nhanh hơn; mean **tăng** 19,4 → 21,1 s; bỏ outlier mỗi bên thì chỉ −7% | ❌ |

**Quyết định: giữ `thinking_condense = True`** — 3/4 tiêu chí đạt nhưng tiêu chí 4 trượt.

Lý do vật lý rất đơn giản: condense chỉ chiếm **~10% pipeline** (1,9 s trong ~18 s), nên 1,3 s tiết kiệm được chìm hoàn toàn trong biên dao động ±20 s của gateway — một case OFF dính 80,9 s là đủ kéo mean vượt cả nhánh ON. Không đổi cấu hình khi lợi ích không đo được, trong khi rủi ro (dù benchmark này chưa quan sát thấy) là loại lỗi âm thầm nhất: condense sai không có lớp nào phía sau bắt được, vì hallucination check chỉ kiểm tra câu trả lời có bám context — mà context thì đã sai từ đầu.

### 9.4. Đính chính một kết luận cũ

Mục 7.4 và comment trong `config.py` từng viện dẫn **một quan sát đơn lẻ** — lượt multi-turn *"Vậy ngày thường thì sao?"* rơi xuống `answerable=False` → escalate khi tắt thinking — làm lý do giữ bật. Benchmark 16 case **không tái hiện được**: chính case ellipsis đó (cd_001) nay đúng ở cả hai nhánh. Nhiều khả năng quan sát cũ là generation variance chứ không phải hệ quả của condense.

Kết luận cuối vẫn là giữ bật, nhưng **lý do đã đổi**: không phải "tắt thì hỏng" mà là "tắt không mang lại lợi ích E2E đo được". Comment trong `config.py` đã sửa cho đúng.

### 9.5. Giới hạn của benchmark này

- **n = 16**, nên p95 và mean rất nhạy với một outlier. Các con số latency ở đây chỉ đủ để nói "không thấy cải thiện rõ", không đủ để nói "chắc chắn không cải thiện".
- Ba failure mode đều bằng 0 ở cả hai nhánh — **có thể do bộ case chưa đủ khó**, không nên đọc thành "condense hoàn hảo". Bộ case dùng history 1 lượt; hội thoại 3+ lượt với nhiều thực thể chồng nhau mới là chỗ dễ gãy.
- Chấm bằng từ khoá xác định (`must_keep` / `expected_answer_keywords`), không dùng LLM judge — tránh circular evaluation nhưng cũng không bắt được lỗi diễn đạt tinh vi.

---

## 10. P2 — Error analysis 7 câu `hr_question → ambiguous` (chưa code)

### 10.1. Tín hiệu đầu tiên: thinking-ON cứu được 6/7

| | Số câu |
|---|---|
| thinking-ON phân loại đúng `hr_question` | **6/7** |
| thinking-ON cũng xếp `ambiguous` | 1/7 (qa_025) |

Theo cách đọc đã thống nhất: ON cứu gần hết ⇒ nghiêng về **reasoning depth**, không phải ontology nhãn sai. Nhưng đúng một câu mà **cả hai nhánh đều xếp ambiguous** — đó là câu đáng nghi nhãn nhất, và soi kỹ thì đúng vậy.

### 10.2. Bảng phân tích

| id | Query | Gold | Fast | ON | Vì sao fast chọn ambiguous | Trả lời được ngay? | Thiếu thông tin gì | Pattern |
|---|---|---|---|---|---|---|---|---|
| qa_002 | *Chủ nhật mình đi làm thêm thì tính lương bao nhiêu?* | hr | amb | **hr** | Gần trùng ví dụ ambiguous **có sẵn trong prompt**: *"Tôi làm cuối tuần thì được tính sao?"* | Có — 200% | Không | **D** |
| qa_003 | *Tự ở lại làm thêm mà không đăng ký trước có được tính OT không?* | hr | amb | **hr** | Có "mình/tự", router thận trọng dù câu đã nêu rõ điều kiện | Có | Không | **A** |
| qa_008 | *Đi công tác tự lo chỗ ở không lấy hóa đơn thì có được hỗ trợ tiền không?* | hr | amb | **hr** | Điều kiện dài + ngôi thứ nhất | Có — khoán 250k/đêm | Không | **A** |
| qa_025 | *Đến ngày thứ 60 thì có đánh giá gì không?* | hr | amb | **amb** | **Câu thiếu ngữ cảnh thật** — ngày thứ 60 của cái gì? | **Không** nếu đứng một mình | Mốc 60 ngày thuộc quy trình nào | **B** |
| qa_036 | *Tôi ốm đột xuất sáng nay mới biết, báo nghỉ kiểu gì?* | hr | amb | **hr** | Gần trùng ví dụ ambiguous trong prompt: *"Tôi bị ốm có được trả lương không?"* | Có — thủ tục báo nghỉ | Không | **D** |
| qa_110 | *Nghỉ việc thì gói bảo hiểm sức khỏe chấm dứt khi nào? Có cách nào duy trì?* | hr | amb | **hr** | Chủ đề bảo hiểm trùng ví dụ ambiguous *"Công ty có hỗ trợ tiền khám bệnh không?"* | Có | Không | **D** |
| qa_111 | *Đăng ký bảo hiểm sức khỏe cho vợ và 2 con thì chi phí thế nào?* | hr | amb | **hr** | Như trên — chủ đề bảo hiểm | Có | Không | **A** |

### 10.3. Root cause chung: 6/7 câu đã nêu rõ CHIỀU hỏi

Điều kiện Ted đặt là **≥ 4/7 cùng một root cause** thì đáng thử prompt fix. Ở đây là **6/7**, và pattern rất cụ thể:

> Cả 6 câu đều **đã chỉ rõ chiều hỏi** — hỏi *số tiền* (qa_002, qa_008, qa_111), *thủ tục* (qa_036), *điều kiện* (qa_003), *thời điểm* (qa_110). Người hỏi không cần được hỏi lại "ý bạn là loại nào" vì họ đã nói rõ họ muốn biết gì.

Trong khi đó, các ví dụ `ambiguous` **đang nằm trong prompt router** lại mập mờ đúng ở chiều hỏi:

| Ví dụ trong prompt (ambiguous) | Câu bị xếp nhầm (gold = hr_question) | Khác nhau ở đâu |
|---|---|---|
| *"Tôi làm cuối tuần thì được tính **sao**?"* | qa_002 *"...thì tính **lương bao nhiêu**?"* | "tính sao" có thể là tiền **hoặc** nghỉ bù; "tính lương bao nhiêu" đã chốt là tiền |
| *"Tôi bị ốm **có được trả lương** không?"* | qa_036 *"...**báo nghỉ kiểu gì**?"* | một hỏi quyền lợi (BHXH hay phép năm?), một hỏi thủ tục |
| *"Công ty có hỗ trợ **tiền khám bệnh** không?"* | qa_110/111 về **gói bảo hiểm sức khỏe của công ty** | một mập mờ BHYT/BHSTN, một đã nêu đúng tên gói |

Tức router đang khái quát hoá theo **chủ đề** (cuối tuần / ốm / bảo hiểm) trong khi ranh giới thật nằm ở **chiều hỏi**. Prompt hiện chưa nói điều đó ra, nên fast router — không có reasoning để tự suy — bám vào ví dụ gần nhất về mặt chủ đề.

### 10.4. Nhóm B: qa_025 nên xem lại nhãn, không phải sửa classifier

*"Đến ngày thứ 60 thì có đánh giá gì không?"* — mốc 60 ngày có thể là thử việc, onboarding, hay thời hạn khác. Câu này được sinh từ `03_quy-trinh-onboarding.md` nên mang ngữ cảnh ngầm của tài liệu, nhưng **đứng một mình thì đúng là mơ hồ**. Cả thinking-ON lẫn fast đều xếp `ambiguous` — hai nhánh độc lập cùng đồng ý là tín hiệu mạnh.

Đây là ca đúng như cảnh báo: **không nên kéo accuracy lên bằng cách ép mọi ambiguous thành hr_question**. Hỏi lại một lượt ở đây là hành vi đúng.

### 10.5. Đề xuất (chưa thực hiện, chờ duyệt)

**Fix:** bổ sung vào prompt router một quy tắc phân định theo *chiều hỏi*, kèm 2–3 cặp ví dụ đối lập lấy thẳng từ bảng 10.3 — làm rõ rằng cùng chủ đề nhưng đã chốt chiều hỏi thì là `hr_question`. **Không thêm LLM call, không thêm nhánh logic** → 0 latency.

**Rủi ro:** nới ranh giới ambiguous có thể làm câu **thật sự** mơ hồ bị kéo sang `hr_question` — bot tự trả lời khi lẽ ra phải hỏi thêm. Đây mới là regression đáng sợ, nên phải rerun **toàn bộ 137 câu**, không chỉ 7 case.

**Acceptance cho P2:**

| Loại | Tiêu chí |
|---|---|
| Primary | Giảm unnecessary clarification (7 câu này) |
| Hard guard | HR false rejection vẫn **= 0** |
| Hard guard | `ambiguous → hr_question` false positive không tăng đáng kể (hiện 1) |
| Hard guard | competitor/out-of-scope safety không regression (hiện 10/10 + 15/15) |
| Hard guard | router p50 vẫn **< 500 ms** |
| Preferred | Không thêm LLM call |

Nếu prompt/examples lấy lại được 3–5/7 câu với 0 latency thì đáng làm. Nếu phải thêm verifier để vớt 1–2 câu cuối thì dừng — router 92% với 0 câu từ chối oan đã đủ tốt, không đáng phá kiến trúc để đuổi headline accuracy.

---

## 11. P2 — Prompt fix theo "chiều hỏi" (kết quả: đề xuất MERGE)

### 11.1. Phát hiện dọc đường: 8/8 ví dụ ambiguous trong prompt là câu nguyên văn từ eval

Khi chuẩn bị thêm ví dụ synthetic, em kiểm tra prompt hiện tại và thấy **cả 8 ví dụ `ambiguous` đều copy nguyên văn từ `qa_eval_set.json`** — chiếm nửa lớp ambiguous (8/16 theo bộ nhãn hiện tại; con số 8/15 ở các ghi chép trước là trạng thái *trước* khi qa_025 được relabel sang `ambiguous`). Con số đầu tiên nhìn rất đáng ngại:

| | Câu ambiguous **có** trong prompt | Câu **không** trong prompt |
|---|---|---|
| thinking ON | 8/8 = 100% | 3/7 = 43% |
| fast + guard | 8/8 = 100% | 3/7 = 43% |

Chênh 57 điểm, và em đã báo cáo đây là "recall lớp ambiguous bị thổi phồng".

### 11.2. Đính chính: kết luận đó SAI — thí nghiệm B bác bỏ nó

Nhánh B thay 8 ví dụ bằng paraphrase synthetic, tức 8 câu đó **không còn nằm trong prompt**. Nếu leakage là nguyên nhân, chúng phải tụt:

| Nhánh | 8 câu từng-leak | 8 câu chưa từng leak |
|---|---|---|
| A (còn leak) | 8/8 | 4/8 |
| **B (đã bỏ leak)** | **8/8** | 4/8 |
| **C (bỏ leak + rule)** | **8/8** | 4/8 |

**Không đổi một câu nào.** Phát biểu đúng mức: *ablation B không cho thấy bằng chứng rằng việc copy nguyên văn 8 eval case vào prompt đã làm tăng accuracy trên chính 8 case đó; sau khi thay bằng paraphrase synthetic, kết quả vẫn 8/8.* Chênh lệch với nhóm còn lại nhiều khả năng phản ánh khác biệt **độ khó**, nhưng benchmark này không được thiết kế để chứng minh nguyên nhân đó — và nhánh B vẫn có paraphrase tương ứng trong prompt, nên không phải điều kiện "không có ví dụ nào".

Đây là lỗi suy luận của em: thấy tương quan (leaked ⇔ đúng) rồi kết luận nhân quả, trong khi biến ẩn là độ khó. Thí nghiệm B chính là phép thử đã bác bỏ nó — và may là nó được chạy trước khi con số "43%" kịp đi vào bất kỳ kết luận nào.

**Vẫn bỏ leakage**, nhưng vì lý do khác: eval case nằm trong prompt khiến mọi số liệu *tương lai* trên lớp đó mất giá trị làm bằng chứng, kể cả khi hôm nay nó vô hại.

> **Bỏ ví dụ bị leak là quyết định vệ sinh đánh giá (evaluation hygiene), KHÔNG phải một cải thiện hiệu năng được tuyên bố.** Ablation A→B không tìm thấy bằng chứng nào cho thấy các ví dụ bị leak chịu trách nhiệm cho accuracy đã quan sát.

Ghi câu trên để người đọc sau không hiểu thành "đã phát hiện leakage làm tăng accuracy".

### 11.3. Ba nhánh, cùng 137 câu, cùng bộ nhãn

| Nhánh | Acc | Cost | **UCR** | **UAR** | HR rejected | OOS leak | p50 |
|---|---|---|---|---|---|---|---|
| A: prompt cũ (có leakage) | 92,7% | 23 | 6/93 | 1/16 | 0 | 0 | 373 ms |
| B: bỏ leakage, chưa có rule | 93,4% | 24 | 4/93 | 1/16 | **1** | 0 | 331 ms |
| **C: B + rule chiều hỏi** | **94,9%** | **17** | **3/93** | **1/16** | **0** | 0 | **332 ms** |

```
UCR = gold hr_question bị đoán ambiguous / tổng gold hr_question
UAR = gold ambiguous bị đoán hr_question / tổng gold ambiguous
```

**Attribution (đọc ở mức thận trọng, n_runs = 1 mỗi nhánh):** bỏ leakage (A→B) gần như trung tính về số — chênh 0,7 điểm nằm trong biên nhiễu. So sánh B→C cho thấy **tín hiệu cải thiện phù hợp với tác động mong đợi của rule chiều hỏi**: accuracy 93,4% → 94,9%, cost 24 → 17 (**B→C: −29%**; tính từ A thì **A→C: −26%** — hai con số này không mâu thuẫn, chỉ khác mốc so), UCR 4 → 3.

Riêng **HR rejected 1 → 0 không được tính là thành quả của rule**: chính report này đã nhận định case của B nhiều khả năng là nhiễu, nên không thể vừa gọi nó là nhiễu vừa ghi công cho việc nó biến mất.

### 11.4. Đối chiếu 6 hard guard

| # | Guard | A → C | |
|---|---|---|---|
| 1 | HR bị từ chối oan = 0 | 0 → **0** | ✅ |
| 2 | **UAR không tăng** *(veto)* | 1/16 → **1/16** | ✅ |
| 3 | out_of_scope/competitor → hr_question | 0 → **0** | ✅ |
| 4 | UCR giảm | 6/93 → **3/93** (−50%) | ✅ |
| 5 | router p50 < 500 ms | 373 → **332 ms** — *không quan sát thấy regression*, dưới guard | ✅ |
| 6 | Không thêm LLM call | không thêm nhánh nào | ✅ |

**Đề xuất: merge C** — trên cơ sở *candidate C đã pass toàn bộ guard định trước*, không phải "C chắc chắn tốt hơn B ở mọi metric". Cứu 3/6 câu bị hỏi lại oan, cost giảm 26% so với A, veto condition không bị chạm, không quan sát thấy latency regression (41 ms chênh lệch nằm trong biên dao động gateway đã đo ở P1 — không claim rule làm router nhanh hơn), và không thêm một dòng kiến trúc nào.

### 11.5. Giới hạn

- Mỗi nhánh chạy **một lần**. Chênh lệch 1–3 câu (≈1–2 điểm) nằm trong biên nhiễu của LLM; ví dụ HR rejected của B (=1) rất có thể là nhiễu chứ không phải hệ quả của việc bỏ ví dụ. Tín hiệu đáng tin ở đây là **hướng nhất quán** (UCR giảm đều 6→4→3, cost giảm mạnh ở C), không phải từng con số lẻ.
- 3 câu UCR còn lại chưa phân tích. Theo tiêu chí đã thống nhất thì **dừng ở đây** — không thêm verifier để vớt nốt, vì router hiện đã đạt cả 6 guard.

### 11.6. Sau P2, bộ 137 câu KHÔNG còn là held-out sạch

Đây là điểm methodology quan trọng nhất của P2, và "0/24 ví dụ trùng eval" **không** đủ để nói benchmark vẫn sạch. Phải tách hai khái niệm:

| Loại | Tình trạng |
|---|---|
| **Verbatim leakage** — copy nguyên câu eval vào prompt | ✅ Đã loại bỏ |
| **Test-informed tuning** — soi lỗi trên eval rồi sửa prompt theo chính các lỗi đó | ⚠️ **Vẫn tồn tại** |

Prompt C được thiết kế **sau khi** đã soi 6/7 failure trong chính `qa_eval_set`; rule "chiều hỏi" và các cặp contrastive synthetic đều sinh ra từ pattern của những failure đó. Dùng một bộ dev để tune là chuyện bình thường trong engineering iteration — nhưng hệ quả phải được ghi rõ:

> **94,9% trên 137 câu là bằng chứng đủ mạnh để chọn C hơn B. Nó KHÔNG phải ước lượng không thiên lệch cho accuracy production.**

Muốn claim thứ hai, cần một **fresh holdout chưa từng được dùng để soi lỗi hay tune prompt**.

**Đổi trạng thái bộ dữ liệu:** từ đây `qa_eval_set.json` được coi là **router development / regression set**, không còn là pristine holdout cho router.

### 11.7. Freeze snapshot ra quyết định

Bốn việc chốt trước merge:

**1. Snapshot dùng để ra quyết định này**

```
eval/datasets/qa_eval_set.json sha256:e7db31d410247a84
src/agents/nodes/router.py sha256:1e48b3337315f48b
config: thinking_router=False · escalation_guard_enabled=True
        thinking_condense/generation/hallucination=True
        router_model=DeepSeek-V4-Flash · low_confidence_threshold=0.2
dataset: 137 câu tính metric (3 câu retired) · nhãn qa_025=ambiguous, qa_051/052/053=competitor_comparison
```

**2. Artifact A/B/C giữ nguyên, không overwrite ở lần chạy sau:** `eval/results/router_prompt_dimension_ab.json` (nhánh C + số của cả 3 nhánh), `router_escalation_guard_ab.json`, `router_thinking_ab.json`.

**3. Con số 94,9% thuộc về CẢ CẤU HÌNH, không phải riêng `thinking_router=False`.** Nó là kết quả cộng dồn của: fast router + escalation guard + contextual competitor rule + dimension rule. Đã ghi vào `src/config.py` để vài tháng sau không ai tưởng chỉ tắt thinking là tự có 94,9%.

**4. Rollback:** nếu tỷ lệ hỏi lại / escalate trên production tăng bất thường → **revert prompt C về revision trước** (bỏ block "PHÂN ĐỊNH ... CHIỀU HỎI"), **không** bật thinking cho toàn bộ traffic ngay. Bật lại thinking là đòn cuối, không phải phản xạ đầu tiên.

### 11.8. Đóng optimization router — bottleneck không còn ở đây

Theo số đo P1:

| Chặng | p50 |
|---|---|
| router | ~0,33 s |
| condense | ~1,93 s |
| **E2E** | **~17,9 s** |

Router chiếm khoảng **2% E2E median**. Cắt thêm 100–200 ms ở đây người dùng gần như không cảm nhận được. Không mở P3 cho router.

Bước hợp lý tiếp theo là **profiling E2E theo node** (condense · router · retrieve · rerank · generate · hallucination check · retry/rewrite), rồi xếp ưu tiên theo:

```
latency contribution × traffic frequency × chi phí chất lượng/an toàn khi tối ưu
```

Nghi ngờ ban đầu: **generate** và **hallucination check** đáng nhìn hơn router nhiều — riêng hallucination check đã đo được 13,9 s trong một lượt ở mục 7.1, và nó là chặng đã bị từ chối tắt thinking vì lý do an toàn.

### 11.9. Fresh holdout — protocol và lý do không mượn `qa_heldout_set`

**Quyết định: nhờ một người khác trong team viết bộ holdout mới 60–80 câu.** Không dùng `qa_heldout_set.json`.

Lý do: 30 câu đó là held-out của **agent end-to-end**. Chạy router trên chúng là tiêu một tài sản có phạm vi rộng hơn để xác nhận đúng một component — trong khi router đã đạt 94,9% với 0 HR rejection và optimization đã đóng. Không đáng đổi. Chỉ mượn nếu team thực sự không tạo được bộ mới và cần quyết định release ngay; khi đó phải ghi vào `eval/results/heldout_runs.md` rằng đã tiêu một phần shared holdout.

Brief đầy đủ cho người viết: [`eval/ROUTER_HOLDOUT_BRIEF.md`](../eval/ROUTER_HOLDOUT_BRIEF.md). Bốn điểm cốt lõi:

**1. Blind.** Người viết không xem 137 câu dev, không xem prompt router, không xem danh sách lỗi hiện tại, không xem mục 10–11 của report này. Chỉ đọc định nghĩa 4 intent + phạm vi corpus. **Không** nhận yêu cầu kiểu "viết thêm câu giống lỗi router đang mắc" — biết router yếu ở đâu rồi cố viết vào đúng chỗ đó thì bộ này mất ý nghĩa.

**2. Phủ đủ, trộn easy/borderline.** 30–40 `hr_question`, 10–15 `ambiguous`, 10–15 `out_of_scope_or_personal`, 5 `greeting` — nhóm cuối bộ dev hiện có **0 câu**. Nhãn chốt **trước** khi chạy.

**3. Chạy đúng một lần.** Script [`eval/scripts/eval_router_holdout.py`](../eval/scripts/eval_router_holdout.py) tự ghi sha256 của dataset + `router.py` + config vào report, và **từ chối chạy nếu report cũ đã tồn tại** — muốn chạy lại phải xoá file bằng tay, tức là một hành động có chủ đích chứ không phải lỡ tay. Lỗi phát hiện được ghi thành *production risk*, **không** dùng để tune vòng này.

**4. Gate theo hướng lỗi, không theo accuracy.** Với 60–80 câu, sai thêm một câu đã dịch ~1,3–1,7 điểm — đòi đúng 94,9% trên mẫu này là đòi sai thống kê.

| Tiêu chí | Ngưỡng |
|---|---|
| HR false rejection | 0, tối đa 1 nếu review được |
| OOS/competitor → `hr_question` | **0** |
| UAR | Không cho thấy bot trở nên liều |
| UCR | Ở mức chấp nhận được |
| Router p50 | < 500 ms |

Accuracy chỉ để tham khảo, kỳ vọng quanh low/mid-90s, **không veto** ở 92–93%. Cách đọc: *92,5% với HR rejection 0 và OOS leak 0* → C được xác nhận. *96% nhưng 2 câu personal/out-of-scope bị route thành `hr_question`* → không đạt, dù headline đẹp hơn.

Sau lần chạy, bộ này thành **router holdout consumed v1**. Không quay lại tune router từ kết quả của nó; đợt optimization mới (nếu có) phải dùng một dev set khác.

---

## 12. Fresh holdout v1 — kết quả (CONSUMED, chạy đúng một lần)

Bộ 70 câu do người khác trong team viết theo [`eval/ROUTER_HOLDOUT_BRIEF.md`](../eval/ROUTER_HOLDOUT_BRIEF.md), chạy một lần duy nhất trên cấu hình C đã freeze.

**Snapshot:** `dataset sha256:f082436e1b901506` · `router.py sha256:1e48b3337315f48b` · `thinking_router=False` · `escalation_guard_enabled=True` · `router_model=DeepSeek-V4-Flash`

### 12.1. Kiểm tra bộ câu trước khi chạy

| Kiểm tra | Kết quả |
|---|---|
| Trùng nguyên văn dev set (137 câu) | **0** |
| Trùng ví dụ trong prompt router | **0** |
| Gần giống dev set (ratio ≥ 0,80) | **0** |
| Trùng lặp nội bộ | **0** |
| Phân bổ vs brief | hr 38 · amb 13 · oos 14 · greeting 5 — đúng khoảng |
| Trộn độ khó | 42 easy / 28 borderline, **mỗi nhóm** đều có cả hai |

### 12.2. Kết quả — cả 5 gate PASS

| Gate | Ngưỡng | Kết quả | |
|---|---|---|---|
| HR false rejection | 0, tối đa 1 nếu review được | **0/38** | ✅ |
| OOS/competitor → `hr_question` | 0 | **0/14** | ✅ |
| UAR | Bot không trở nên liều | 1/13 (dev: 1/16) | ✅ |
| UCR | Ở mức chấp nhận được | 2/38 (dev: 3/93) | ✅ |
| Router p50 | < 500 ms | **324 ms** | ✅ |

**Accuracy 94,3% (66/70)** — chỉ để tham khảo, không phải gate.

| Nhóm | Đúng | | Độ khó | Đúng |
|---|---|---|---|---|
| `greeting` | **5/5** | | easy | 40/42 = 95% |
| `hr_question` | 36/38 = 95% | | borderline | 26/28 = 93% |
| `ambiguous` | 11/13 = 85% | | | |
| `out_of_scope_or_personal` | **14/14** | | | |

### 12.3. Nhận xét

**1. Không thấy dấu hiệu overfit lên dev set.** Holdout 94,3% so với dev 94,9% — chênh 0,6 điểm, tức 0,4 câu trên mẫu 70. Đây là kết quả có ý nghĩa nhất của lần chạy: prompt C được thiết kế từ pattern lỗi của dev set, nên rủi ro lớn nhất là nó chỉ hợp với chính bộ đó. Số liệu không cho thấy điều đó xảy ra. Vẫn phải nói đúng mức: n = 70 nên 0,6 điểm nằm trọn trong biên nhiễu — kết luận đúng là *"không quan sát thấy overfit"*, không phải *"đã chứng minh tổng quát hoá tốt"*.

**2. Hai nhánh đắt nhất đều sạch tuyệt đối.** 0/38 câu HR bị từ chối oan và 0/14 câu out-of-scope/personal lọt thành `hr_question`. Nhóm sau đáng chú ý hơn: 14 câu gồm cả 3 dạng (dữ liệu cá nhân, công ty khác, ngoài phạm vi HR) và có 5 câu borderline — trong đó *"so với Vinamilk thì trợ cấp công tác của V-NOVA bên nào cao hơn?"* nhắc **cả** tên công ty khác lẫn công ty nội bộ, vẫn bị chặn đúng.

**3. `greeting` 5/5 — lần đầu tiên nhánh này được đo.** Dev set có 0 câu greeting; router có nhánh `direct` cho nó nhưng chưa từng có bằng chứng nào. Giờ có, dù mẫu nhỏ.

**4. Bốn câu sai đều nằm ở ranh giới `hr_question` ↔ `ambiguous`**, không câu nào chạm nhánh an toàn:

| id | Câu | Gold → Pred | Nhận xét |
|---|---|---|---|
| rh_009 | *nếu tháng này có ngày lễ mà mình vẫn đi làm thì tiền công tính sao?* | hr → amb | Có chiều hỏi rõ ("tiền công"), lẽ ra rule chiều hỏi phải bắt được. Đây là miss thật của rule. |
| rh_029 | *công ty có chính sách hỗ trợ chi phí học chứng chỉ chuyên môn không* | hr → amb | Rơi đúng chủ đề đào tạo — chủ đề mà prompt có ví dụ ambiguous *"tài trợ việc học thêm"*. Router vẫn khái quát theo chủ đề ở ca này. |
| rh_053 | *mình ký rồi thì có đổi được nữa không* | amb → oos | Sai **hướng an toàn** (hỏi lại → escalate), phiền hơn nhưng không liều. |
| rh_055 | *em muốn làm thủ tục thì bắt đầu từ đâu* | amb → hr | Ca duy nhất bot **tự tin quá mức**; đây là dạng lỗi UAR cần theo dõi. |

Hai câu rh_009 và rh_029 cho thấy rule chiều hỏi **chưa phủ hết** — vẫn còn ca mà router bám chủ đề thay vì chiều hỏi. Theo protocol, những câu này được ghi thành **production risk / nguồn cho dataset sau**, **không** dùng để tune tiếp vòng này.

**5. Latency p95 = 506 ms, max 686 ms.** p50 324 ms đạt gate thoải mái; p95 nhích qua mốc 500 ms nhưng gate đặt trên p50 nên không vi phạm — ghi lại để lần profiling E2E tới có mốc so.

### 12.4. Kết luận

**Cấu hình C được xác nhận trên dữ liệu chưa từng thấy.** Bộ này giờ là **router holdout consumed v1** — script đã tự khoá, chạy lại phải xoá report bằng tay. Không quay lại tune router từ 4 câu sai ở trên.

Router đóng tại: **94,3% trên holdout · 0 HR false rejection · 0 OOS leak · p50 324 ms · 0 kiến trúc thêm.**

---

## 13. P3 — E2E latency profiling baseline (chỉ đo, chưa tối ưu)

Workload cố định 35 request ([`eval/datasets/e2e_profiling_workload.json`](../eval/datasets/e2e_profiling_workload.json)), phủ 10 nhóm. Kết quả đầy đủ: `eval/results/e2e_profile_baseline.json`.

### 13.1. Phân phối E2E

| p50 | p75 | p90 | p95 | mean | max |
|---|---|---|---|---|---|
| **11,2 s** | 17,3 s | 27,2 s | 39,1 s | 15,2 s | **93,5 s** |

`> 30 s`: **8,6%** (3 request) · `> 60 s`: **2,9%** (1 request)

**Hai loại retry hoàn toàn khác nhau, đừng đọc lẫn:**

| Loại | Tỷ lệ |
|---|---|
| Transport/API retry (429, 5xx) | **0%** |
| Semantic hallucination retry (FAIL → regenerate) | **2/20 lần check = 10%** |

**Critical path: `sum(node) = wall = 15.161 ms`, phần ngoài node = 0 ms.** Không quan sát thấy overlap đáng kể giữa các node trong workload này — tổng thời gian node khớp wall time. Hệ quả thực dụng: mỗi giây cắt được ở một node rơi thẳng vào E2E, nên ROI của optimization tính được trực tiếp. (Phát biểu này gắn với graph hiện tại; nếu sau này thêm nhánh chạy song song thì phải đo lại.)

### 13.2. Xếp hạng theo expected contribution (workload-weighted)

> **Đây là workload-weighted contribution, KHÔNG phải production contribution.** Workload 35 câu được cố ý thiết kế để phủ đủ scenario (10 HR · 5 multi-turn · 4 ambiguous · 5 OOS/competitor · 4 retrieval khó · 2 greeting...), nên `Exec%` ở đây là tần suất *trong bộ profiling*, không phải tần suất traffic thật. Nếu production có 90% câu HR thì contribution của generate/hallucination còn cao hơn; nếu nhiều greeting/OOS thì thấp hơn. Bảng này đủ để **chọn target**, nhưng muốn nói *"tối ưu X giảm production latency Y%"* thì cần traffic mix thật.

| Node | Exec% | p50 | mean khi chạy | max | **Expected** | **%E2E** |
|---|---|---|---|---|---|---|
| **generate** | 66% | 7,5 s | 9,9 s | 31,4 s | **6,48 s** | **43%** |
| **hallucination_check** | 57% | 4,2 s | 9,5 s | **60,0 s** | **5,42 s** | **36%** |
| clarify | 11% | 9,2 s | 10,7 s | 18,2 s | 1,22 s | 8% |
| retrieve | 66% | 1,0 s | 1,1 s | 3,7 s | 0,75 s | 5% |
| router | 100% | 0,35 s | 0,59 s | 5,9 s | 0,59 s | 4% |
| condense | 100% | 0,001 s | 0,38 s | 5,2 s | 0,38 s | 2% |
| direct | 6% | 5,5 s | 5,5 s | 5,6 s | 0,31 s | 2% |
| grade / confidence / escalate / finalize | — | ~1 ms | — | — | ~0 | 0% |

**`generate` + `hallucination_check` = 79% E2E.** Nghi ngờ ban đầu (hallucination đứng đầu) **sai**: generate mới là node lớn nhất. Nhưng khoảng cách không lớn và hai node gắn với nhau — hallucination check nhận đầu vào từ generate, và khi nó FAIL thì generate chạy lại.

### 13.3. Ba phát hiện quan trọng hơn thứ hạng

**1. Retry hallucination là đuôi phân phối, không phải chi phí thường trực.**

| | n | p50 hallucination | E2E mean |
|---|---|---|---|
| Không retry | 18 (90%) | **4,0 s** | 17,2 s |
| **Có retry** | 2 (10%) | **38,4 s** | **61,9 s** |

Chỉ 10% lần check phải retry, nhưng chúng kéo E2E lên gấp 3,6 lần.

**Đính chính một claim em viết sai ở bản trước:** retry **không** giải thích toàn bộ tail. Đối chiếu 3 request `> 30 s`:

| Request | E2E | hallucination retry |
|---|---|---|
| wl_13 | 93,5 s | 1 |
| **wl_30** | **59,7 s** | **0** |
| wl_06 | 30,3 s | 2 |

Phát biểu đúng: *retry là nguồn tail lớn nhất quan sát được — cả 2 request có semantic retry đều vượt 30 s, và một trong số đó tạo ra max 93,5 s. Nhưng 1/3 request `> 30 s` (wl_30) hoàn toàn không retry.* Với `> 60 s` thì n = 1 nên chỉ nói được: *request duy nhất vượt 60 s trong mẫu này có retry.*

Hệ quả cho bước sau: **single-pass generation/check cũng tự nó tạo được extreme latency** (wl_30: 3 LLM call, 4.462 completion token, không retry lần nào). Nghiên cứu tail không được chỉ nhìn retry path.

Ngoài ra: p50 hallucination chỉ 4 s nhưng mean 9,5 s và max 60 s — trung vị và trung bình kể hai câu chuyện khác nhau, và cái đuôi mới là thứ người dùng nhớ.

**2. Toàn bộ chi phí nằm ở GLM-5.2 với thinking bật.**

| Model | thinking | Số call | Tổng thời gian | comp_tok TB | prompt_tok TB |
|---|---|---|---|---|---|
| **GLM-5.2** | mặc định (bật) | 58 | **480,9 s** | **561** | 1.711 |
| DeepSeek-V4-Flash | tắt | 31 | 14,9 s | 4 | 2.196 |
| DeepSeek-V4-Flash | mặc định | 1 | 5,5 s | 412 | 754 |

58 call GLM-5.2 chiếm **96% tổng wall time của các lệnh gọi `chat`** — lưu ý mẫu số: bảng này lọc `kind == "chat"` nên **chưa** gồm embedding và rerank (retrieve đóng góp riêng ~5% E2E). Trung bình 561 completion token/call, so với 31 call fast router sinh **4 token/call** tốn tổng 14,9 s.

So sánh này gợi ý mạnh rằng lượng token sinh ra là driver chính, nhưng **ba biến đổi cùng lúc** (model family, thinking on/off, độ dài output) nên tự nó chưa chứng minh quan hệ nhân quả. Phân tích within-model ở 13.3b tách được điều đó.

### 13.3b. Within-model: token sinh ra thực sự là driver

Để tách ba biến trộn ở trên, phân tích riêng **58 lệnh gọi GLM-5.2** — cùng model, cùng thiết lập thinking, chỉ khác độ dài input/output:

| Tương quan (Spearman) | Hệ số |
|---|---|
| duration ↔ **completion tokens** | **+0,895** |
| duration ↔ prompt tokens | +0,246 |

| Completion tokens | n | median latency | median prompt tokens |
|---|---|---|---|
| 0–200 | 12 | **1,98 s** | 489 |
| 200–500 | 24 | **4,36 s** | 1.260 |
| 500–1.000 | 15 | **10,01 s** | 1.041 |
| > 1.000 | 7 | **15,03 s** | 3.567 |

Biến đối chứng — bucket theo **prompt** tokens thì quan hệ gãy: nhóm 1.000–2.000 (4,95 s) còn *nhanh hơn* nhóm 0–1.000 (5,28 s). Nhóm 2.000–4.000 chậm hơn (7,23 s) nhưng completion token của nó cũng cao hơn (510 vs 317), tức vẫn là completion kéo chứ không phải prompt.

**Throughput đo được: median 75,1 token/s.** Con số này biến mọi thứ thành số học đơn giản: muốn cắt 5 giây thì phải bớt ~375 token sinh ra.

Phát biểu đúng mức: *dữ liệu nhất quán với giả thuyết lượng token sinh ra là driver chính của chat latency, và within-model correlation +0,895 vs +0,246 ủng hộ mạnh giả thuyết đó.* Vẫn là quan sát tương quan trên dữ liệu tự nhiên, không phải thí nghiệm can thiệp — nhưng đủ để định hướng: **mọi optimization latency đáng giá đều phải đi qua việc giảm token sinh ra.**

**3. `clarify` và `direct` là hai node bị bỏ quên.** Cả hai chỉ sinh một câu ngắn nhưng đang chạy GLM-5.2 với thinking bật: clarify p50 **9,2 s**, direct **5,5 s**. Chúng nằm ở nhánh mà người dùng kỳ vọng phản hồi *nhanh nhất* — hỏi lại một câu, hoặc chào hỏi. Một câu chào tốn 5,8 s (nhóm `greeting` p50).

### 13.4. E2E theo nhóm request

| Nhóm | n | p50 | LLM call TB |
|---|---|---|---|
| retrieval_hard | 4 | 18,1 s | 3,0 |
| multi_turn_condense | 5 | 15,7 s | 4,2 |
| hr_single_turn | 10 | 14,3 s | 3,1 |
| guardrail_pii | 1 | 10,0 s | 3,0 |
| escalate_low_confidence | 3 | 9,9 s | 2,0 |
| ambiguous | 4 | 9,6 s | 2,0 |
| greeting | 2 | 5,8 s | 2,0 |
| guardrail_injection | 1 | 0,40 s | 1,0 |
| out_of_scope_personal | 3 | 0,38 s | 1,3 |
| **competitor** | 2 | **0,003 s** | **0** |

Nhánh chặn sớm (competitor / personal) gần như miễn phí — rule deterministic chặn trước mọi lệnh gọi mạng. Đây là bằng chứng cho thấy các guard rẻ đặt đúng chỗ.

### 13.5. Kết quả này dùng để làm gì

Theo đúng phạm vi P3: **chưa đề xuất tối ưu**. Ba quan sát định hướng cho việc chọn target:

- **generate (43%) và hallucination_check (36%)** là hai ứng viên duy nhất đáng mở. Mọi node còn lại cộng lại chỉ 21%, và router/condense — hai thứ vừa tốn nhiều công nhất — chỉ chiếm 6%.
- Với hallucination_check, câu hỏi **không phải** "tắt thinking không" (đã có bằng chứng ở mục 7.6 rằng tắt làm lớp an toàn dễ dãi hơn: 10/13 bất đồng theo hướng FAIL→PASS). Hướng đáng xét là **giảm số lần gọi** (10% retry đang tạo ra toàn bộ đuôi > 30 s), **bỏ check khi không cần**, hoặc **giảm token phải sinh**.
- `clarify`/`direct` tuy chỉ 10% E2E nhưng là **quick win rõ ràng nhất**: sinh một câu ngắn mà tốn 9,2 s / 5,5 s vì đang dùng GLM-5.2 thinking bật, trong khi đây là hai nhánh cần phản hồi nhanh nhất về mặt trải nghiệm.

Baseline này freeze cùng workload v1. Mọi so sánh optimization sau phải chạy đúng workload đó.

### 13.6. Hai cải tiến cho profiler (áp dụng từ lần đo sau)

**1. Tách `Visit%` và `LLM-call%`.** Cột `Exec%` hiện tại mang nghĩa *node được graph ghé qua*, không phải *node thực sự tốn tiền*. Rõ nhất ở `condense`: visit 100% nhưng p50 chỉ 1 ms — vì phần lớn request không có `history` nên node no-op ngay, chỉ 5/35 request (**14%**) thực sự gọi LLM. Router cũng vậy: visit 100% nhưng 2 request competitor bị rule chặn trước khi gọi model, nên LLM-call% ≈ 94%.

Đọc `Exec% = 100%` mà không biết điều này sẽ tưởng condense chạy đầy đủ trên mọi request.

**2. Gắn từng lệnh gọi mạng vào node phát sinh ra nó.** Hiện `llm_trace` ghi danh sách call phẳng theo thứ tự thời gian, chưa gắn với node. Có gắn thì mới bóc được "generate tốn 9,9 s gồm bao nhiêu cho reasoning và bao nhiêu cho câu trả lời" mà không phải suy đoán.

### 13.7. Roadmap P4 (chưa thực hiện)

| Giai đoạn | Mục tiêu | Vì sao xếp thứ tự này |
|---|---|---|
| **P4A** — cheap-path cleanup (`direct`, `clarify`) | Bỏ GLM-5.2 thinking khỏi hai nhánh chỉ sinh một câu ngắn | Contribution chỉ ~10% nhưng **profile latency/độ phức tạp xấu nhất**: user gõ *"hello"* chờ ~5,8 s; hỏi lại một câu tốn 9,2 s. Effort nhỏ, risk thấp, A/B dễ, UX cải thiện thấy ngay. Cùng dạng tác vụ mà router đã chứng minh tắt thinking hiệu quả |
| **P4B** — generate | Target lớn nhất (43%) | Nhưng **không bắt đầu bằng "tắt thinking"**. Phải bóc 9,9 s đó thành reasoning token vs answer token vs verbosity trước — nếu một câu trả lời 150 từ kèm 800 token reasoning thì mới có căn cứ. Chấm bằng answer correctness + citation faithfulness + answerability, không chỉ latency |
| **P4C** — hallucination check | 36%, nhưng **safety-critical** | Phải tách hai bài toán: **normal path** (90%, ~4 s — giảm chi phí thường trực) và **retry path** (10%, ~38 s — giảm xác suất retry hoặc chi phí mỗi retry). Hai thứ này **không benchmark chung**. Và câu hỏi tuyệt đối không phải "tắt thinking" — mục 7.6 đã có bằng chứng tắt làm lớp an toàn dễ dãi hơn (10/13 bất đồng theo hướng FAIL→PASS) |

**Không quay lại** router, condense, retrieval ở giai đoạn này — baseline đã chỉ rõ chúng cộng lại chỉ 11% E2E.

---

## 14. P4A — cheap-path cleanup (`direct` + `clarify`)

Hai experiment độc lập, hai bộ gate riêng. Dataset: [`eval/datasets/p4a_cheap_path_set.json`](../eval/datasets/p4a_cheap_path_set.json) — 10 câu greeting viết mới, 12 câu ambiguous **lấy nguyên văn** từ dev set (đã verify khớp 12/12 và đều `type=ambiguous`).

### 14.1. Gate v1 sai, phải sửa rồi chấm lại

Bản gate đầu cho kết quả *"template thắng tuyệt đối 10/10, GLM chỉ 8/10"*. Soi từng câu thì cả ba check đều có false positive:

| Check | Lỗi | Bằng chứng |
|---|---|---|
| `is_greeting` | Thiếu nhóm phản hồi lời cảm ơn | GLM trả *"Dạ, không có gì ạ!"* cho *"cảm ơn bạn nhiều"* — đúng ngữ cảnh nhưng bị chấm trượt |
| `no_policy_number` | Phạt cả số **trích lại từ câu hỏi gốc** | 4/4 ca trượt đều là *"3 ngày"* (từ *"nghỉ 3 ngày"*) và *"60 ngày"* (từ *"ngày thứ 60"*) — nhắc lại để xác nhận ngữ cảnh là hành vi đúng |
| `offers_options` | Chỉ khớp từ khoá cứng | **7/7** câu bị chấm trượt đều có từ nối lựa chọn (*"hay"/"hoặc"*), tức đều nêu đủ phương án — chỉ diễn đạt khác bộ từ khoá |

Gate v2 sửa cả ba, thêm `context_appropriate` (trả lời lời cảm ơn bằng lời chào mở đầu là lệch ngữ cảnh — điểm yếu mà gate v1 không thể thấy). **Chấm lại trên đúng output đã lưu, 0 API call** — cùng dữ liệu, chỉ khác thước đo.

### 14.2. Kết quả sau khi sửa gate — kết luận đảo ngược

**`direct`** (10 câu greeting):

| Variant | Pass | p50 | p95 | `context_appropriate` |
|---|---|---|---|---|
| **A — GLM hiện tại** | **10/10** | 5,16 s | 6,95 s | **10/10** |
| B — template | 8/10 | **0 ms** | 0 ms | **8/10** |
| C — fast LLM (DeepSeek, thinking tắt) | 8/10 | 2,00 s | 2,67 s | **8/10** |

Cả B và C trượt đúng 2 câu, và trượt **cùng một chỗ**: input là lời cảm ơn (*"cảm ơn bạn nhiều"*, *"ok thanks nhé"*) mà trả lời mở đầu bằng lời chào.

- **B (template)**: trả cùng một câu cho mọi input — *"Chào bạn, mình là trợ lý HR nội bộ..."*. Người dùng nói *cảm ơn* nhận lại lời chào giới thiệu.
- **C (fast LLM)**: *"Chào bạn! Rất vui khi được hỗ trợ bạn 😊..."* — vẫn chào, vẫn lệch.
- **A (GLM)**: *"Dạ, không có gì ạ!..."* — đúng ngữ cảnh.

Tức greeting **không phải tác vụ đóng như em giả định**: nó gồm ít nhất hai loại (mở đầu và kết thúc/cảm ơn), và trả lời phải khác nhau.

**`clarify`** (12 câu ambiguous):

| Variant | Pass | p50 | p95 | mean |
|---|---|---|---|---|
| A — GLM + thinking | 11/12 | 5,49 s | 8,78 s | 5,95 s |
| **B — DeepSeek fast, thinking tắt** | **11/12** | **1,43 s** | 3,29 s | 1,74 s |

**Per-check giống hệt nhau ở cả 6 tiêu chí**: `is_question` 12/12 · `no_invented_number` 11/12 · `on_topic` 12/12 · `offers_options` 12/12 · `concise` 12/12 · `non_empty` 12/12.

Câu trượt duy nhất là cl_10 ở **cả hai** variant, và trượt vì cùng lý do — nhắc *"60 ngày thử việc"* trong khi câu gốc chỉ nói *"ngày thứ 60"*, tức suy ra "thử việc" là ngữ cảnh chưa được xác nhận. Đây là hành vi của prompt, không phải của model.

### 14.3. Đề xuất

**`clarify` → merge variant B.** Chất lượng hoà tuyệt đối trên cả 6 check, latency **5,49 s → 1,43 s (3,8x)**. Đúng loại đánh đổi cần tìm: nhanh hơn nhiều, không mất gì đo được.

**`direct` → chưa merge cả B lẫn C.** Cả hai đều sai ngữ cảnh ở nhóm "cảm ơn/kết thúc hội thoại". Hai hướng xử lý, cần Ted chọn:

1. **Template phân nhánh** — tách hai mẫu câu (mở đầu / phản hồi cảm ơn) bằng một điều kiện từ khoá deterministic. Vẫn 0 ms, vẫn không thể bịa chính sách, sửa đúng chỗ đang sai. Rủi ro: phân nhánh bằng từ khoá sẽ có ca lọt.
2. **Fast LLM + sửa prompt** — `_DIRECT_SYSTEM` hiện chỉ nói "trả lời lời chào/câu xã giao", chưa phân biệt mở đầu với kết thúc. Bổ sung một câu vào prompt rồi đo lại C. Giữ được tính tự nhiên, chi phí 2,0 s (vẫn nhanh 2,6x so với A).

Em nghiêng về **(2)**: 2 giây cho một câu chào vẫn là cải thiện lớn so với 5,2 giây, và nó giữ được khả năng phản hồi đúng ngữ cảnh mà template khó bắt kịp. Nhưng đây là đánh đổi UX/độ phức tạp nên Ted quyết.

### 14.4. Conditional E2E (không dùng overall p50)

Hai path này chỉ chạy trên một phần traffic, nên phải đọc theo request đi qua chúng:

| Loại request | Trước | Sau (nếu merge clarify B) |
|---|---|---|
| Câu `ambiguous` (P3: E2E p50 9,59 s) | clarify tốn 9,24 s | clarify còn ~1,43 s → **E2E ~5,8 s** |
| Câu `greeting` (P3: E2E p50 5,82 s) | direct tốn 5,50 s | chưa chốt phương án |

Ghi nhận đúng phạm vi: đây là ước tính từ latency node đo riêng, chưa chạy lại E2E đầy đủ. Sau khi chốt phương án `direct`, cần chạy lại workload v1 để có số E2E thật.

### 14.5. Direct v2 — kết quả, và một cảnh báo về chính cách chấm

Sau khi viết lại `_DIRECT_SYSTEM` theo speech act và mở rộng dataset lên 17 câu phủ 7 act:

| Cách chấm | A (GLM) | C (fast LLM) |
|---|---|---|
| **Gate v3** (viết trước khi chạy) | 15/17 | 14/17 |
| **Gate v4** (sửa sau khi xem kết quả) | **17/17** | **17/17** |

**Phải nói thẳng: đây là lần thứ tư em sửa gate, và lần này sửa SAU khi đã nhìn kết quả.** Đó đúng là kiểu thao tác dễ trượt thành "chỉnh thước đo tới khi ra con số mình muốn". Hai lỗi mà v4 sửa:

- Tiếng Việt dùng *"chào bạn"* cho **cả** mở đầu lẫn tạm biệt. Câu *"Chào bạn, đi làm vui vẻ nhé!"* trả lời cho *"thôi mình đi làm đây, chào bạn"* là lời tạm biệt hoàn toàn đúng, nhưng v3 bắt lỗi bằng tiền tố nên phạt oan **cả hai** variant.
- Câu hỏi năng lực và câu xã giao (*"bạn làm việc cuối tuần luôn à?"*) cần **trả lời nội dung**, không cần từ chào — v3 đòi có từ chào là đòi sai thứ.

**Lý do em vẫn cho rằng kết luận đứng vững: nó không đổi giữa hai thước đo.** Ở cả v3 lẫn v4, A và C trượt **đúng cùng những câu** (dr_14 goodbye, dr_16 casual_social); khác biệt duy nhất là dr_05 mà C trượt ở v3. Tức phát biểu *"chất lượng C tương đương A"* ổn định bất kể chấm bằng gate nào — còn nếu Ted muốn giữ v3 làm chuẩn thì tiêu chí "mọi check ≥ GLM" **không đạt** (14 < 15) và C chưa được merge. Đây là quyết định của Ted, em không tự chọn gate có lợi hơn.

**Latency thì không phụ thuộc gate:**

| | p50 | p95 | max |
|---|---|---|---|
| A — GLM | 4,97 s | 11,52 s | **183,8 s** |
| **C — fast LLM** | **0,96 s** | **5,20 s** | 16,7 s |

Nhanh **5,2x** ở p50, **2,2x** ở p95. Đáng chú ý riêng: một câu chào ở nhánh A từng mất **183,8 giây** — đuôi này tự nó là lập luận độc lập cho việc rời khỏi GLM ở nhánh xã giao.

### 14.6. Bài học: proxy heuristic ≠ semantic quality

Bốn lần gate sai trong P4A đều cùng một dạng lỗi, đáng ghi lại vì nó nguy hiểm hơn bất kỳ con số nào trong mục này:

| Giả định của gate | Thực tế |
|---|---|
| Có số kèm đơn vị = bịa chính sách | Nhắc lại số **từ chính câu hỏi** là hành vi đúng |
| Không khớp từ khoá = thiếu lựa chọn | 7/7 câu bị phạt đều có *"hay/hoặc"*, tức đủ lựa chọn |
| Intent tên là `greeting` = phải trả lời bằng lời chào | Nhóm này gồm ≥ 6 speech act, phần lớn **không** cần chào |
| *"chào bạn"* ở đầu câu = mở đầu hội thoại | Tiếng Việt dùng chung từ này cho lời tạm biệt |

Nếu giữ gate v1, em đã merge phương án template dựa trên một benchmark sai. Cách sửa em dùng — **đổi evaluator rồi chấm lại trên observation đã lưu, không gọi lại API** — giữ được dữ liệu gốc nguyên vẹn và tách bạch "đo cái gì" khỏi "đo được gì". Nhưng nó chỉ hợp lệ khi việc sửa dựa trên **nguyên tắc áp dụng cho mọi câu**, không phải trên câu cụ thể nào vừa trượt.

### 14.7. Chấm mù nhánh `direct` — freeze tiêu chí TRƯỚC khi chấm

Ba trạng thái của evaluator, tách bạch để không lẫn vai trò:

| Evaluator | Trạng thái | Dùng làm gì |
|---|---|---|
| **Gate v3** | **Bị loại** — chứa tiêu chí không áp dụng đúng cho mọi speech act (dr_05: câu hỏi năng lực trả lời đúng nhưng bị phạt vì thiếu lời chào) | Không dùng để quyết định |
| **Gate v4** | Đã sửa, nhưng **post-hoc** (sửa sau khi xem output) | Chỉ dùng cho phân tích khám phá |
| **Chấm mù bởi người** | Chưa chạy | **Bằng chứng quyết định** cho A vs C |

Điểm cần tách rạch ròi: dr_05 đủ để **loại v3 khỏi vai trò chuẩn quyết định**, nhưng **không** đủ để tự động chứng minh C ngang A. Hai chuyện khác nhau.

**Không rerun API.** Vấn đề nằm ở người đo, không nằm ở thiếu quan sát — chạy lại chỉ thêm nhiễu ngẫu nhiên vào một câu hỏi vốn không phải về nhiễu.

**Bộ chấm đã xuất:** [`eval/datasets/p4a_direct_blind_review.md`](../eval/datasets/p4a_direct_blind_review.md) — 34 mẫu (17 A + 17 C), ID trung tính `sample_001`…`sample_034`, đã xáo với seed cố định. Kiểm tra tự động sau khi xuất: **0 cặp cùng input nằm cạnh nhau**, **0 từ khoá lộ nguồn gốc** (không có tên model, variant, latency, hay kết quả gate). Người chấm cũng không được cho biết mục đích của phép so sánh. Mapping giải mã lưu riêng ở `eval/results/p4a_direct_blind_mapping.json`, không đưa cho người chấm.

**Hai câu hỏi chấm** (freeze trước khi người chấm mở file):

- **Q1 — Phản hồi có đúng ngữ cảnh không?** Đáp đúng điều người dùng vừa nói; không mở đầu lại hội thoại bằng lời chào giới thiệu khi người dùng đang cảm ơn/tạm biệt; câu hỏi năng lực và câu xã giao phải được trả lời đúng nội dung (không bắt buộc chào).
- **Q2 — Có tự đưa ra số liệu/quy định HR không?** Chỉ tính khi con số/quy định **không** có trong câu người dùng.

**Decision rule (freeze trước):**

```
merge C  <=>  context_appropriate(C) >= context_appropriate(A)
              AND invented_policy(C) <= invented_policy(A)
```

**Hoà cũng merge**, vì latency là bằng chứng độc lập và rất lớn: p50 4,97 s → 0,96 s (5,2x) · p95 11,52 s → 5,20 s · max 183,8 s → 16,7 s.

**C thua dù chỉ một câu → không merge**, và **không sửa evaluator lần thứ năm** để cứu kết quả; thay vào đó đọc annotation để xác định đó có phải một failure class thật của fast model hay không.

Hai script cưỡng chế quy trình thay vì chỉ ghi trong tài liệu: `export_direct_blind_review.py` từ chối xuất lại nếu mapping đã tồn tại (xuất lại sẽ đổi thứ tự và làm hỏng phiếu đang lưu hành), còn `score_direct_blind_review.py` từ chối giải mã khi phiếu chưa điền đủ — giải mã nửa chừng rồi nhìn số là mở đường cho bias.

### 14.8. Chấm mù — kết quả và merge

Người chấm (Ted) đọc 34 mẫu ẩn nhãn, chấm theo đúng 2 câu hỏi đã freeze:

| | context appropriate | tự bịa số liệu HR |
|---|---|---|
| A — GLM | **17/17** | 0/17 |
| C — fast LLM | **17/17** | 0/17 |

Decision rule freeze trước được thoả (`C ≥ A` và `C ≤ A`) → **merge C**. `direct_mode = "fast_llm"`.

Ba mẫu người chấm ghi chú (004, 007, 008) chính là chỗ **cả gate v3 lẫn v4 đều vấp**: *"chào bạn"* nằm trong câu tạm biệt (*"hẹn gặp lại"*, *"đi làm vui vẻ"*). Người đọc phân biệt được ngay bằng ngữ nghĩa toàn câu; heuristic văn bản thì không. Đây là minh hoạ cụ thể nhất cho bài học ở 14.6.

**Hai giới hạn phải ghi đúng mức:**

1. **Rubric này không phân biệt được A với C** (34/34 và 0/34 — trần ở cả hai phía). Nó chứng minh *"C không có lỗi thô nào mà A không có"*, **không** chứng minh *"chất lượng tinh tế hai bên ngang nhau"*. Với kết quả kịch trần, phép đo hết power để phát hiện khác biệt nếu có. Quyết định merge vì vậy đứng chủ yếu trên **latency** — đúng như decision rule đã dự liệu khi viết "hoà cũng merge".
2. Người chấm **blind về nhãn** (không biết mẫu nào của model nào — phần quan trọng nhất, vì không thể uốn kết quả theo variant) nhưng **không blind về mục đích** của đợt tối ưu.

**Không chọn `template`** dù nó 0 ms: benchmark cho thấy một câu cố định cho mọi input làm sai ngữ cảnh ở nhóm cảm ơn/tạm biệt. `greeting` là *tên intent của router*, nhưng bên trong có ít nhất 7 speech act — template hoá nhóm này sẽ đẻ ra một mini-router bằng từ khoá, đúng thứ vừa bỏ công loại bỏ ở tầng trên.

### 14.9. Rerun frozen workload v1 — và vì sao KHÔNG được đọc E2E overall

| E2E | Trước P4A | Sau P4A |
|---|---|---|
| p50 | 11,24 s | **15,27 s** |
| mean | 15,16 s | **22,04 s** |
| > 30 s | 8,6% | **17,1%** |
| > 60 s | 2,9% | **5,7%** |

Nhìn thẳng thì E2E **xấu đi**. Nhưng so từng node cho thấy chuyện khác:

| Node | Trước | Sau | Tỷ lệ | Nhóm |
|---|---|---|---|---|
| **clarify** | 9,24 s | **1,09 s** | **0,12x** | P4A đụng |
| **direct** | 5,50 s | **2,99 s** | **0,54x** | P4A đụng |
| retrieve | 1,00 s | 3,89 s | **3,90x** | *không đụng* |
| hallucination_check | 4,24 s | 5,86 s | 1,38x | *không đụng* |
| router | 0,35 s | 0,52 s | 1,48x | *không đụng* |
| generate | 7,51 s | 6,16 s | 0,82x | *không đụng* |

**`retrieve` chậm đi 3,9 lần dù P4A không đụng một dòng nào của nó.** Nó là chuỗi embedding + vector search + rerank, tức thuần mạng — không có cách nào để thay đổi ở `direct`/`clarify` làm nó chậm đi. Hai dấu hiệu khác cùng hướng: request có retry mạng **0% → 5,7%**, và `generate` max **31,4 s → 201,1 s**.

Kết luận đúng: **lần chạy sau rơi vào điều kiện gateway xấu hơn hẳn**, nên hai lần chạy này **không so được overall với nhau**. Đây đúng là bài học đã rút ở P1 (mục 6.1 của `CONDENSE_EVAL_SPEC`): so hai lần chạy khác thời điểm trên một gateway biến động là không đáng tin, và biến động ở đây lớn hơn cả hiệu ứng đang muốn đo.

**Thứ đọc được — *within-run category contrast*, trên chính các nhóm đi qua hai path đã sửa.** Gọi đúng tên vì đây KHÔNG phải causal A/B hoàn chỉnh: nó so các nhóm request *trong cùng một phiên*, nên loại được nhiễu giữa hai phiên nhưng không thay thế được paired interleaved test nếu muốn claim E2E delta chính xác.

| Nhóm request | Trước | Sau | |
|---|---|---|---|
| **ambiguous** (đi qua `clarify`) | 9,59 s | **1,77 s** | **0,18x** |
| **greeting** (đi qua `direct`) | 5,82 s | **3,61 s** | **0,62x** |
| hr_single_turn (không đụng) | 14,30 s | 23,01 s | 1,61x |
| retrieval_hard (không đụng) | 18,15 s | 17,92 s | 0,99x |

Hai nhóm mục tiêu cải thiện mạnh **ngay cả khi môi trường xấu hơn** — nhóm đối chứng `hr_single_turn` chậm đi 1,61x trong cùng lần chạy. Ước tính ở 14.4 (*ambiguous 9,59 s → ~5,8 s*) hoá ra còn **bảo thủ**: observed là 1,77 s.

**Đóng P4A với phát biểu đúng phạm vi:** cải thiện ở `direct` và `clarify` là thật, đo được ở cả mức node lẫn mức nhóm request. Tác động lên E2E overall **chưa kết luận được** từ lần chạy này.

**Chuẩn phương pháp cho mọi P4 về sau:** với gateway biến động như hiện tại, A/B phải **paired/interleaved trong cùng cửa sổ thời gian** —

```
A1, B1, A2, B2, ...        hoặc  randomize per request
KHÔNG:  chạy toàn A hôm nay, toàn B lúc khác
```

Lần rerun này là minh chứng: biến động giữa hai phiên (`retrieve` ×3,9 dù không đụng tới) lớn hơn chính hiệu ứng đang đo.

---

## 15. P4B Tier 1 — profiling generate (chỉ đo, chưa A/B)

Chạy trên workload v1 cố định, với instrument mới: node attribution + tách `reasoning_content`/`content` + đo riêng Chroma. **Attribution sạch: 0/184 call không gán được node.**

### 15.1. Hai blind spot mà P3 chưa thấy

**(a) `retrieve` từng là hộp đen gộp bốn thứ khác bản chất.** Sau khi bóc:

| Thành phần | n | p50 | p95 | max | contrib/req |
|---|---|---|---|---|---|
| `vector_search` (Chroma query) | 23 | 999 ms | 9,66 s | 10,3 s | 1.521 ms |
| `chroma_init` (cold start) | 23 | **0 ms** | 0 ms | **12,55 s** | 359 ms |
| `rerank` | 23 | 282 ms | 747 ms | 1,91 s | 261 ms |
| `embedding` | 23 | 191 ms | 1,04 s | 2,11 s | 231 ms |

`chroma_init` chỉ thực sự chạy **1/23 lần (4%)** — đúng request đầu mỗi tiến trình, tốn 12,55 s; 22 lần còn lại là 0 ms nhờ `lru_cache`. Đây là **cold-start tax**, không phải chi phí thường trực, và hướng xử lý khác hẳn: prewarm lúc service startup.

**(b) Ba node dùng chung GLM-5.2 + thinking bật** (`condense`, `generate`, `hallucination_check`) nên không phân biệt được bằng metadata lệnh gọi. Nếu chạy profiling mà không gán node, reasoning của hallucination sẽ bị cộng nhầm vào generate.

### 15.2. `vector_search` KHÔNG phải bottleneck thường trực — P4B tiếp tục

Smoke test 3 request cho 12–14 s và làm dấy lên nghi ngờ phải đổi roadmap. Full workload bác bỏ điều đó:

| p50 | p75 | p90 | p95 | max | mean |
|---|---|---|---|---|---|
| **999 ms** | 1,97 s | 6,93 s | 9,66 s | 10,3 s | 2,32 s |

Phân phối rõ ràng **bimodal**: `0–2s: 17` · `2–5s: 3` · `5–10s: 2` · `>10s: 1`. Tức đa số truy vấn ~1 giây, có một cái đuôi nhỏ — đúng dạng tail issue của hạ tầng, không phải degradation toàn cục. Ba smoke case rơi trúng cửa sổ xấu.

**Kết luận: không mở P4R retrieval. P4B tiếp tục như kế hoạch.**

### 15.3. Xếp hạng component — và một outlier quyết định thứ hạng

| Component | contrib/req (đầy đủ) | contrib/req (trimmed, bỏ 1 max) |
|---|---|---|
| `hallucination_check` | **9.013 ms** | 3.164 ms |
| `generate` | 5.103 ms | **4.340 ms** |

**Hai kết luận cùng đúng, không cái nào thay thế cái nào:**

- Theo **typical/trimmed contribution**, `generate` là node đắt nhất → đây là target optimization.
- Theo **tail**, `hallucination_check` vẫn là nguồn đuôi lớn nhất, và call 204,7 s là một sự cố **có thật** phải giữ trong mọi báo cáo về tail — không được nói như thể nó không tồn tại.

Chi tiết call đó:

```
204.718 ms · comp_tok=2.720 · reasoning=8.959 chars · answer=4 chars
throughput 13,3 tok/s  (median của node này: 98 tok/s)  · attempts=2
```

Throughput 13,3 tok/s so với 98 tok/s bình thường ⇒ đây là **gateway stall**, không phải "model suy luận quá nhiều". Nó là lý do vì sao xếp hạng theo contribution đầy đủ và theo trimmed contribution cho hai thứ tự khác nhau — và cũng là lý do tắt thinking **không** chữa được loại tail này.

Đây đúng là ca mà P3 đã cảnh báo: tail latency không chỉ do retry, và tắt thinking **không chữa được** loại tail này.

### 15.4. Reasoning vs answer — bằng chứng cho P4B

| Node | n | p50 | completion (median) | reasoning | answer | **share** | throughput |
|---|---|---|---|---|---|---|---|
| `generate` | 26 | 4,79 s | 480 tok | 1.374 chars | 285 chars | **0,840** | 97,7 tok/s |
| `hallucination_check` | 23 | 5,16 s | 389 tok | 1.353 chars | **4 chars** | **0,997** | 98,1 tok/s |
| `condense` | 5 | 1,45 s | 130 tok | 475 chars | 64 chars | 0,849 | 84,7 tok/s |

**`hallucination_check` sinh trung vị 1.353 ký tự suy luận để trả về đúng 4 ký tự (`PASS`).** Tỷ lệ output không tới người dùng là **99,7%**. Đây là node lãng phí nhất về reasoning-to-useful-output — nhưng cũng là node **khó tối ưu nhất**, vì mục 7.6 đã chứng minh tắt thinking ở đây làm lớp an toàn dễ dãi hơn (10/13 bất đồng theo hướng FAIL→PASS).

**Correlation (Spearman) — trả lời đúng câu hỏi "latency đi theo cái gì":**

| Node | ↔ completion_tok | ↔ reasoning_chars | ↔ answer_chars | ↔ prompt_tok |
|---|---|---|---|---|
| `generate` | **+0,912** | **+0,804** | +0,335 | +0,041 |
| `hallucination_check` | +0,883 | **+0,889** | +0,105 | +0,108 |

Hai điều đọc được: **prompt gần như không ảnh hưởng** (+0,041 / +0,108 — nhồi context vào gần như miễn phí), và **answer_chars tương quan yếu hơn hẳn reasoning_chars**. Với `generate`, hai biến này có thể đồng biến (câu khó → reasoning dài → answer cũng dài), nhưng chênh lệch +0,804 vs +0,335 vẫn nghiêng mạnh về reasoning.

### 15.5. Phân loại 5 generate call chậm nhất

| duration | comp_tok | reasoning | answer | throughput | Phân loại |
|---|---|---|---|---|---|
| 26,70 s | 2.747 | 11.454 | 345 | 102,9 tok/s | **reasoning-bound** |
| 24,12 s | 1.282 | 3.811 | 333 | 53,2 tok/s | reasoning-bound |
| 10,65 s | 524 | 1.591 | 208 | 49,2 tok/s | reasoning-bound |
| 9,61 s | 939 | 3.142 | 310 | 97,7 tok/s | reasoning-bound |
| 9,33 s | 1.082 | 3.644 | 209 | 116,0 tok/s | reasoning-bound |

**5/5 đều reasoning-bound, không có ca answer-bound hay gateway-stall.** Case chậm nhất sinh 11.454 ký tự suy luận cho 345 ký tự trả lời — và throughput 102,9 tok/s là **bình thường**, tức nó chậm vì *sinh quá nhiều*, không phải vì hạ tầng.

### 15.6. Kết luận Tier 1 và điều kiện sang Tier 2

Ba câu hỏi P4B đặt ra ban đầu đã có trả lời:

1. **Generate sinh bao nhiêu reasoning so với answer?** Trung vị 1.374 vs 285 ký tự — **84% output là suy luận nội bộ**.
2. **Latency có đi theo reasoning không?** Có: +0,804 với reasoning, +0,335 với answer, +0,041 với prompt.
3. **Các case chậm nhất do đâu?** 5/5 là reasoning-bound với throughput bình thường.

⇒ **Giả thuyết "reasoning là target chính của generate" được dữ liệu ủng hộ mạnh.** Đủ điều kiện mở A/B thinking ON/OFF cho `generate`.

**Nhưng A/B đó phải theo đúng hai ràng buộc đã thống nhất:**

- **Paired/interleaved randomize** trong cùng cửa sổ thời gian (`A→B`, `B→A` xen kẽ), báo bằng `median(paired_delta)` + p25/p75, không phải hiệu hai p50.
- **Hai tầng, tầng 2 có quyền veto**: generate nhanh hơn mà làm hallucination FAIL nhiều hơn thì E2E vẫn chậm hơn do retry. Trong lần đo này đã có 3/35 request phải retry (`wl_08`, `wl_11`, `wl_14`), và lần generate thứ hai tốn xấp xỉ lần đầu (p50 4,88 s vs 4,71 s) — tức mỗi lần FAIL là mất thêm gần trọn một lượt generate cộng một lượt check.

Quality gate cho Tier 1 của A/B: answer correctness · grounding/citation · answerable (sentinel) — chấm bằng rubric semantic hoặc judge độc lập, **không** dùng heuristic đơn giản, đúng bài học 14.6.

---

## 16. P4B Tier 2 — A/B `thinking_generation` ON vs OFF

Thiết kế: **isolate** (replay cùng chunks, không rerun cả graph) · **paired + randomize thứ tự trong cặp** · **downstream hallucination có quyền veto**. n = 23 request đi qua `generate`.

### 16.1. Tier 2A — latency

| | v1 | v2 (regex đã sửa) |
|---|---|---|
| median paired delta (OFF−ON) | −5.045 ms | **−4.893 ms** |
| p25 / p75 | −9.150 / −2.556 ms | **−12.068 / −2.790 ms** |
| OFF nhanh hơn | 23/23 | **22/23** |
| generate p50 | 6,55 → 1,78 s | **7,24 → 2,64 s** |

**Cả khoảng p25–p75 đều âm** — khác hẳn P1 (condense) nơi khoảng này bao trùm 0 và đó là lý do bác bỏ. Hai lần chạy độc lập cho cùng kết luận.

### 16.2. Tier 2B — downstream veto

| | ON | OFF |
|---|---|---|
| hallucination PASS (v1) | 20/23 | 23/23 |
| hallucination PASS (v2) | 20/23 | **22/23** |
| hallucination p50 | 6,24 s | 6,11 s |

OFF **không** làm hallucination FAIL nhiều hơn — thực tế còn ít hơn, nhất quán qua hai lần chạy (ON luôn 20/23).

### 16.3. Gate grounding sai hai lần — và lần sửa thứ hai xoá lợi thế của OFF

Check `no_ungrounded_number` (hard gate quan trọng nhất: *wrong confident answer*) sai hai lần vì hai lý do khác nhau:

| Bản | Lỗi | Hệ quả |
|---|---|---|
| v1 | Regex `\d+(?:[.,]\d+)?` **cắt sai số Việt Nam**: `5.310.000 đồng` → `310.000 đồng` | Số cụt không khớp context → đếm nhầm là bịa |
| v2 | Đòi khớp **cả đơn vị**: tìm chuỗi `"5.310.000 đồng"` trong context | Context viết số trong bảng hoặc kèm đơn vị khác cách → vẫn trượt |

Soi từng cờ với context đã lưu: **mọi số bị gắn ungrounded đều có gốc trong nguồn** — `5.310.000` có 2 lần, `11` có 4 lần, `07` có 4 lần. Grounding thật là *con số có trong nguồn hay không*, không phải *chuỗi số-kèm-đơn-vị có khớp nguyên văn hay không*.

Chấm lại theo con số (0 API call, nhờ đã lưu `chunk_texts`):

| | ON | OFF |
|---|---|---|
| Cách cũ (khớp cả đơn vị) | 8 | 4 |
| **Cách đúng (khớp con số)** | **0** | **0** |

**Điểm cần nhấn:** lần sửa gate này làm OFF **mất** một lợi thế đang có (từ "OFF bịa ít hơn một nửa" thành "hoà tuyệt đối"), chứ không phải thêm. Đó là kiểm chứng rằng việc sửa đi theo bằng chứng chứ không theo kết quả mong muốn — điều đáng lo ở lần sửa thứ tư của P4A.

### 16.4. Ba câu ON trượt hallucination — một cơ chế đáng ghi

| id | ON | OFF |
|---|---|---|
| wl_05 | *"...tổng cộng **07 tháng**"* — tự cộng 6+1 | *"...nghỉ thai sản 06 tháng..."* — bám nguyên văn |
| wl_14 | *"...cứ mỗi con được nghỉ thêm... **07 tháng**"* | *"...được nghỉ thêm 01 tháng cho con thứ hai"* |
| wl_28 | Diễn giải rộng hơn về chủ hộ kinh doanh | Trả lời sát nguồn, có gạch đầu dòng |

Giả thuyết ban đầu (*"ON viết dài hơn nên nhiều số hơn"*) **bị bác bỏ**: độ dài trung vị 284c (ON) vs 290c (OFF), gần bằng nhau.

Cơ chế thật có vẻ khác: **thinking làm model TỔNG HỢP nhiều hơn** — tự cộng `06 + 01 = 07 tháng` rồi nêu kết quả suy ra. Con số đó **đúng về logic** nhưng không có nguyên văn trong context, nên hallucination checker — vốn kiểm tra "câu trả lời có bám sát đoạn trích không" — đánh trượt.

Đây là một đánh đổi tinh tế đáng ghi lại: reasoning cho câu trả lời *hữu ích hơn* (đã tính sẵn cho người dùng) nhưng *khó grounding hơn* theo đúng nghĩa đen của lớp kiểm chứng hiện tại. Không phải model bịa — mà là hai định nghĩa "đúng" đang xung đột.

### 16.5. Đối chiếu 5 hard gate (freeze trước khi chạy)

| # | Gate | Kết quả | |
|---|---|---|---|
| 1 | Wrong confident answer không tăng | ungrounded **0 vs 0** | ✅ |
| 2 | Grounding/citation không regression | citations_valid 23/23 vs 23/23 · has_citation 22 vs **23** | ✅ |
| 3 | Hallucination FAIL/retry không tăng | PASS 20/23 → **22/23** | ✅ |
| 4 | Final answer correctness không giảm | answer_keywords_hit **23/23 vs 23/23** | ✅ |
| 5 | Latency giảm rõ ở paired delta | median **−4,89 s**, p25–p75 đều âm, 22/23 cặp | ✅ |

**Cả 5 gate đạt. Đề xuất merge `thinking_generation = False`.**

### 16.6. Giới hạn

- n = 23, mỗi cặp chạy một lần. Hai lần chạy độc lập cho kết quả nhất quán (median paired delta −5,05 s và −4,89 s; ON luôn 20/23 hallucination PASS), nhưng đây vẫn là mẫu nhỏ.
- Quality chấm bằng tín hiệu xác định, **không** LLM judge. Nó bắt được citation hợp lệ, số bịa, sentinel — **không** bắt được lỗi diễn đạt tinh vi hay câu trả lời đúng-nhưng-lạc-trọng-tâm. Với một thay đổi ở tầng sinh nội dung, đây là giới hạn thật; nếu Ted muốn chắc hơn thì bước tiếp là **chấm mù bởi người** trên 46 câu trả lời (23 cặp), đúng cách đã dùng ở P4A cho `direct`.
- Chưa chạy **paired/interleaved E2E confirmation** — theo đúng thứ tự đã thống nhất: isolate → downstream → E2E confirm.
