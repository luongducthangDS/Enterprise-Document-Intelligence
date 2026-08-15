# HR Helpdesk Assistant — Kế hoạch hoàn thiện v1

> Tài liệu thống nhất duy nhất cho cả team (4 người) — thay thế phần scope/positioning trong PRD & Brief cũ (vốn viết cho tên gọi "HR Document Intelligence Agent", nay đã lỗi thời).
> **Deadline v1: 20/8/2026.** Hôm nay: 16/8/2026 → còn 5 ngày. (Lịch gốc soạn 15/8 dự kiến 6 ngày; task Ngày 1 chưa xong hết nên nén lại còn 5 ngày, giữ nguyên mốc freeze 19/8 tối và demo 20/8.)
> PRD/Brief cũ (`docs/project/prd/`, `docs/project/brief/`) **không bị xoá** — vẫn là nguồn tham chiếu cho phần chưa đổi (data requirements, NFR, evaluation plan). Tài liệu này **ghi đè phần scope/tên gọi/ưu tiên v1** khi có mâu thuẫn.

---

## 0. Đổi tên: vì sao và đổi gì

**Tên cũ:** HR Document Intelligence Agent — định vị quanh việc "tra cứu tài liệu".
**Tên mới:** **HR Helpdesk Assistant** — định vị quanh việc "hỏi HR bất cứ điều gì: trả lời ngay nếu đủ căn cứ, hoặc nối đúng người nếu không".

Đây không phải đổi tên suông — hệ thống đã có sẵn 2 mảnh ghép đúng tinh thần "helpdesk" nhưng trước giờ bị coi là tính năng phụ:
- Cơ chế phân mức tự động hoá `ANSWER / GUIDE / PREPARE_AND_HANDOFF / HUMAN_FIRST` (`docs/project/hr_interaction_boundary_plan.md`)
- Hệ thống ticket/escalation khi agent không đủ thẩm quyền trả lời

→ v1 **nâng ticket + boundary escalation thành tính năng lõi**, không còn là fallback. Đổi lại, phần "kho tài liệu" (document metadata, version, ingestion) **không phải trọng tâm PR** — nó đã đủ dùng, chỉ cần ổn định, không cần mở rộng thêm trong 6 ngày này.

### Thay đổi scope cụ thể so với PRD cũ

| Giữ nguyên (đã đúng, không động) | Thay đổi ưu tiên cho v1 |
|---|---|
| RAG Q&A có citation, đa lượt, 4 refusal state | Ticket phải **thật** (có auth, có persistence, requester xem được trạng thái) — nâng từ P2 lên **P0 cho v1** |
| Non-goals: không payroll, không PII nhạy cảm, không tư vấn pháp lý | Copy UI/empty-state đổi giọng: từ "tra cứu tài liệu" → "hỏi HR, được trả lời hoặc được nối người phù hợp" |
| Personas, 4 loại refusal, evaluation layers | Bỏ khỏi v1 (đẩy sang v2): feedback UI, RBAC retrieval-level, latency 3-5s lý tưởng, multi-chunk recall nâng cao |

---

## 1. Team & phân vai — trọng tâm dồn vào Agent

**Bối cảnh (Ted xác nhận 15/8):** FE và BE core đến giờ đã ổn định, không còn là điểm nghẽn. Agent là nơi còn nhiều vấn đề nhất (G3-G6 trong Phase F triage) và là rủi ro lớn nhất cho deadline 20/8 → **3 người chia nhau toàn bộ phần Agent để làm song song**.

**Cập nhật vai trò (Ted xác nhận lần 2):** Ted chuyển hẳn sang **PM — không code, không trực tiếp review từng dòng code**. 3 thành viên còn lại nhận **toàn bộ task còn lại**, kể cả phần trước đó gán cho Ted (G6, chạy eval, tích hợp lõi `graph.py`/`state.py`/`service.py`).

| Người | Vai trò | Việc chính |
|---|---|---|
| **Ted (Lương Đức Thắng)** | **PM** | Theo dõi tiến độ theo bảng mục 3 hàng ngày, gỡ block/quyết định (như mục 6), chốt cắt giảm theo mục 5 nếu trễ, điều phối Ngày 4 integration + Ngày 6 demo, viết báo cáo bàn giao cuối. Không code, không review kỹ thuật. |
| **hthanhson** | Backend core + Agent | **G3** (router/boundary "ambiguous", 5 case) **+ G6 (đồng sở hữu cùng Dương, xem dưới)** + ticket API thật + chat job durability |
| **Dương** | Frontend + Agent | **G4** (`human_first_required` bắt nhầm từ khoá, `nodes/escalation.py`) **+ G6 (đồng sở hữu cùng hthanhson ngay từ Ngày 1**, không đợi xong G4 mới qua) + UI ticket/boundary + copy đổi định vị |
| **minhphu** | Backend phụ + Agent + quản lý tiến độ | **G5** (retrieval miss, `nodes/retrieval.py`, qa_013/qa_122) + migration sync + **RLS confirm** (chuyển từ hthanhson, cùng mảng schema) + worker execution (ingestion/index/evaluation) + chạy eval đo release gate + WORKLOG/JOURNAL |

**Cân lại tải (theo yêu cầu chia đều 16/8):** G6 — bug khó nhất — từ "hthanhson một mình, Dương giúp nếu rảnh" đổi thành **đồng sở hữu thật sự giữa hthanhson và Dương ngay từ Ngày 1**: hthanhson dẫn dắt root-cause + fix logic, Dương làm cùng phần test/verify từng case (qa_003/qa_047/qa_107/qa_109/qa_123). RLS confirm chuyển từ hthanhson sang minhphu (đã cùng mảng migration/schema, không phải việc mới). Kết quả: mỗi người phụ trách chính đúng 1 bug + 2 việc infra, không ai một mình gánh 2 bug nặng.

⚠️ **Rủi ro cần theo dõi:**
- **Không còn ai review code Agent theo vai trò domain expert.** Thay bằng **peer review chéo bắt buộc**: hthanhson review PR của Dương, Dương review PR của minhphu, minhphu review PR của hthanhson (xem mục 2). Ted chỉ được kéo vào nếu peer review phát hiện thứ vượt quá khả năng quyết của cả 3.
- Tích hợp `graph.py`/`state.py`/`service.py` (nối 4 bug fix lại thành 1 graph chạy được) không còn ai giữ riêng — xử lý chung cả team ở Ngày 4 (mục 3).

---

## 2. Ranh giới file — quy tắc chống xung đột

| Vùng | Owner chính | Ai được sửa | Ghi chú |
|---|---|---|---|
| `frontend/**` | Dương | Chỉ Dương | Người khác cần đổi UI → tạo issue, không tự sửa |
| `backend/app/api/routes/tickets*`, `chat*`, `conversations*`, `auth*` | hthanhson | Chỉ hthanhson | |
| `backend/app/api/routes/ingestion_jobs*`, `index_jobs*`, `evaluation_runs*`, `backend/app/workers/**` | minhphu | Chỉ minhphu | |
| `src/agents/nodes/router.py` | hthanhson | hthanhson (G3) | |
| `src/agents/nodes/escalation.py`, `src/agents/boundary.py` | Dương | Dương (G4) | |
| `src/agents/nodes/retrieval.py` | minhphu | minhphu (G5) | |
| `src/agents/nodes/generation.py`, phần tính confidence | hthanhson + Dương (đồng sở hữu) | Cả hai (G6) từ Ngày 1, không chờ ai rảnh mới vào | |
| `src/agents/graph.py`, `src/agents/state.py`, `src/agents/service.py` (wiring lõi) | Cả 3 | Xử lý chung Ngày 4 (integration), không ai tự ý sửa trước đó | |
| `src/workers/**`, `scripts/rag_pipeline/**`, `eval/**` | minhphu | minhphu | |
| **File dùng chung (contract) — CHẠM LÀ PHẢI BÁO TRƯỚC:** `backend/app/schemas/agent.py`, `backend/app/services/agent_answer_adapter.py`, `src/agents/boundary.py`, `src/agents/state.py` | hthanhson chủ trì | Cả 3, nhưng PR nhỏ, báo trong nhóm chat trước khi mở PR | Đây là nơi từng gãy contract BE↔Agent trước đây — không đổi âm thầm |

**Peer review chéo (thay cho Ted review, vì Ted giờ là PM):** hthanhson review PR của Dương → Dương review PR của minhphu → minhphu review PR của hthanhson. Mỗi PR cần đúng 1 người trong vòng này approve trước khi merge `develop`.

**Git flow áp dụng nguyên bản `GIT-FLOW.md`:** nhánh `feature/<tên>-<mô-tả-ngắn>` từ `develop`, rebase + squash 1 commit trước khi mở PR, ≥1 reviewer approve, không merge `develop` vào `feature` (chỉ rebase), `push --force-with-lease`.

**Thêm riêng cho sprint 6 ngày này:**
- **Xong task thì commit và mở PR về `develop` ngay** (không đợi hết ngày, không đợi hết tuần) — mỗi task trong bảng lịch trình mục 3 là 1 đơn vị commit/PR. Tránh để task tự phình to hoặc gộp nhiều task vào 1 PR khó review.
- Ai đổi file "dùng chung" ở bảng trên → nhắn nhóm trước khi mở PR, PR review trong ngày.
- 19/8 tối: **code freeze**. 20/8 chỉ sửa bug demo-blocking, không thêm tính năng.

---

## 3. Lịch trình theo ngày (đã nén còn 5 ngày, tính từ 16/8)

### Ngày 1 — 16/8 (hôm nay — gộp phần dở dang của kế hoạch gốc + bắt đầu fix)

| Ai | Việc | Deliverable |
|---|---|---|
| hthanhson | **Chốt nốt: dùng `backend/` (JWT tự chế)** làm backend duy nhất, xoá/archive `src/api/` (nếu hôm qua chưa xong). Đọc `router.py`/`boundary.py` → bắt đầu sửa G3. Cùng Dương đọc `nodes/generation.py` xác nhận root cause G6 | `src/api/` gỡ khỏi runtime; G3 bắt đầu có fix; root cause note G6 (chung) |
| Dương | Đọc `nodes/escalation.py` → bắt đầu sửa G4. Cùng hthanhson đọc `nodes/generation.py` cho G6 (đồng sở hữu từ hôm nay) | G4 bắt đầu có fix; root cause note G6 (chung) |
| minhphu | Đọc `nodes/retrieval.py` → bắt đầu sửa G5 (qa_013). Rà soát agent workers từ PR #21 (`4fc9ea7`) — cái gì chạy thật, cái gì còn `QUEUED` mãi | G5 bắt đầu có fix; danh sách gap 3 worker |
| Ted (PM) | Xác nhận cả 3 đã unblock (backend, root-cause) trước cuối ngày; cập nhật mục 6 nếu có quyết định mới phát sinh | — |

### Ngày 2 — 17/8

| Ai | Việc |
|---|---|
| hthanhson | Hoàn thiện G3; cùng Dương tiếp tục G6 → hạ `low_confidence_threshold` 0.5→0.2 (đã chốt); song song ticket API thật (auth + persistence, trên `backend/` đã chốt) |
| Dương | Hoàn thiện G4; cùng hthanhson tiếp tục G6 (viết test/verify từng case qa_003/qa_047/qa_107/qa_109/qa_123); song song UI trạng thái ticket/escalation theo `boundary.runtime_action`; fix history role mismatch phía FE |
| minhphu | Hoàn thiện G5; song song đồng bộ migration (5 bảng thiếu) + bắt đầu RLS confirm (`0003` đã apply thật lên Supabase chưa) |
| Ted (PM) | Theo dõi PR đầu tiên của mỗi người qua vòng peer review (mục 2); nếu ai chưa có PR nào cuối ngày → hỏi ngay |

### Ngày 3 — 18/8

| Ai | Việc |
|---|---|
| hthanhson | Hoàn thiện G6 cùng Dương (ưu tiên xong trước Ngày 4); ticket API thật; chat job durability (startup recover `QUEUED`/`GENERATING`) |
| Dương | Hoàn thiện G6 cùng hthanhson; UI ticket/boundary; copy toàn app đổi theo định vị Helpdesk Assistant; polish loading/error/retry theo NFR-06 |
| minhphu | Hoàn thiện RLS confirm; wiring index-rebuild + evaluation worker (thực thi thật); chạy **eval sơ bộ** trên các fix đã có để chuẩn bị Ngày 4 |
| Ted (PM) | Kiểm tra tiến độ so với mục 5 (cắt giảm) — nếu G6 hoặc 1 trong 3 bug chính chưa xong cuối ngày, quyết định áp dụng cắt giảm ngay |

### Ngày 4 — 19/8 (Integration + Bug bash + Freeze — gộp làm 1 ngày vì lịch đã nén)

Cả 3 (hthanhson, Dương, minhphu) merge hết vào `develop`, cùng nối `graph.py`/`state.py`/`service.py` (không ai giữ riêng nữa — xem mục 2), test end-to-end cùng nhau, sửa lỗi phát hiện ngay trong ngày. **minhphu chạy full eval** trên held-out set thật, ghi số liệu **trung thực** dù chưa đạt ngưỡng lý tưởng. minhphu cập nhật `WORKLOG.md`/`JOURNAL.md`/`README.md` (đổi sang tên "HR Helpdesk Assistant"). Ted (PM) tổng hợp kết quả thành báo cáo, theo dõi checklist mục 4, xác nhận đủ điều kiện freeze. **Code freeze cuối ngày** — chỉ merge fix demo-blocking sau mốc này.

### Ngày 5 — 20/8 (Deadline)

Không code mới. Ted (PM) chủ trì demo rehearsal, kiểm tra bản deploy ổn định cùng cả 3, tag `v1`, viết báo cáo bàn giao cuối cùng (known limitations ghi rõ, không che số liệu).

---

## 4. Definition of Done — v1 (20/8)

- [ ] 1 backend duy nhất, backend còn lại đã gỡ khỏi repo
- [ ] Ticket tạo thật, có auth, requester xem được trạng thái
- [ ] 3 agent worker (ingestion/index/evaluation) chạy hết vòng đời, không đứng ở `QUEUED`
- [ ] Migration repo tái dựng đủ schema đang chạy thật (đủ 10 bảng)
- [ ] RLS đã xác nhận apply trên Supabase thật
- [ ] Chat request durable qua restart
- [ ] History role nhất quán FE/BE
- [ ] G3/G4/G5/G6 (eval Phase F) đã fix, eval chạy lại trên held-out, số liệu ghi trung thực trong báo cáo bàn giao — **đã chốt: release gate (Citation ≥85%/Answer ≥80%/Recall@5 ≥85%) không bắt buộc đạt trước 20/8**, chỉ bắt buộc đo đúng và báo cáo trung thực
- [ ] Copy toàn app phản ánh định vị "HR Helpdesk Assistant"
- [ ] `WORKLOG.md`/`JOURNAL.md`/`README.md` cập nhật đến 20/8
- [ ] Known limitations ghi rõ trong báo cáo bàn giao

**Đẩy sang v2 (không làm trong 6 ngày này):** feedback UI, RBAC retrieval-level theo phòng ban, latency 3-5s, multi-chunk recall nâng cao, human-label ground truth độc lập.

---

## 5. Rủi ro & phương án cắt giảm

**Đã Ted xác nhận thứ tự cắt bên dưới (không đổi thành ưu tiên độ chính xác RAG trước).**

Nếu đến hết Ngày 3 (18/8 tối, ngay trước Integration day) mà một trong các mảng sau chưa xong, **cắt theo thứ tự này** để giữ deadline (không cắt ticket/backend — đó là xương sống định vị mới):

1. Cắt trước: G4/G5 (router/retrieval fix nhỏ lẻ) — ghi vào known limitations, không chặn demo.
2. Cắt tiếp: index-rebuild worker / evaluation worker thực thi đầy đủ — giữ ingestion worker (quan trọng nhất) chạy được, 2 worker còn lại có thể demo bằng dữ liệu đã index sẵn.
3. Không cắt: ticket thật, 1 backend duy nhất, chat durability — đây là 3 điều nếu thiếu thì "Helpdesk Assistant" không còn đúng tên.

---

## 6. Quyết định đã chốt (15/8)

| Quyết định | Chốt bởi | Kết quả |
|---|---|---|
| Backend duy nhất | Ted | **`backend/` (JWT tự chế)** — `src/api/` gỡ khỏi luồng chính |
| `low_confidence_threshold` | Ted | **0.2** (từ 0.5) — ưu tiên trả lời được nhiều hơn, chấp nhận lọt thêm out-of-scope |
| Release gate (Citation/Answer/Recall@5) cho v1 | Ted | **Không bắt buộc đạt trước 20/8**, chỉ bắt buộc đo đúng + báo cáo trung thực |
| Thứ tự cắt giảm nếu trễ tiến độ | Ted | Giữ nguyên mục 5 — không đổi ưu tiên sang "độ chính xác RAG trước" |

| Tên "HR Helpdesk Assistant" áp dụng ở đâu | Ted | **README + slide pitch.** UI đã nằm sẵn trong việc của Dương (mục 3, Ngày 3 — đổi copy toàn app) nên không cần quyết định riêng. minhphu cập nhật README song song lúc dọn `WORKLOG`/`JOURNAL` Ngày 5 |
