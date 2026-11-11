# Tasks

## Đã xong (11/2026)
- [x] Demo public cho nhà tuyển dụng trên Render (05/11)
- [x] Chế độ tool-calling `AGENT_MODE=react` + MCP server (`569b216`, đã push, chạy trên demo)
- [x] Vá rò rỉ ACL, SSE tiến trình tool (`b54771e`)
- [x] Trajectory eval, CREATE_CASE có người duyệt, tool tính phép năm (`5257273`)
- [x] Code chuyển sang Gemini + reindex collection riêng (`5d8b952`)
- [x] React: search trong cùng lượt chạy song song, cache query trùng, báo model khi search không có chunk mới (11/11, chưa đo live)

## Nâng cấp agentic (kế hoạch 11/11, làm lần lượt)
Hiện có: ReAct 4 tool (≤4 vòng), MCP chỉ có `ask_documents`, ACL fail-closed + RBAC, bảng `audit_logs` (chỉ cho admin/knowledge, chưa ghi tool call), CREATE_CASE có xác nhận (migration 0014), `llm_trace` (chỉ bật trong eval), trajectory eval 12 câu chọn tool + 67 câu chi phí, so sánh 2 kiến trúc (pipeline, react). Thiếu: planner, kiểm schema tham số, task state/checkpointer, resume/reject, log mỗi lần chạy, argument accuracy, task success cho việc nhiều bước, nhánh RAG thuần và react+memory.
- [ ] U0 Baseline Gemini: reindex vào Chroma local (không ghi Cloud), chạy eval_agent + trajectory cho pipeline và react; số này là mốc so sánh cho U1–U7
- [x] U1 Tool registry: một chỗ khai báo tool (tên, pydantic args → JSON schema, quyền, có ghi hay không, timeout); tham số sai schema trả lỗi cho model sửa thay vì chạy; timeout/exception thành kết quả tool có cấu trúc; MCP server đọc từ registry
- [x] U2 Observability (agent): `src/observability/run_log.py`, mỗi lần chạy 1 bản ghi `[run]` (stdout + JSONL nếu đặt `RUN_LOG_PATH`): trajectory, tool + tham số, latency từng bước, lỗi, retry, token theo model, chi phí ước tính; nội dung chỉ ghi khi `RUN_LOG_CONTENT=true` (đã che PII)
- [ ] U2b Lưu run log vào Supabase `agent_runs` (migration mới, backend ghi khi nhận kết quả agent) + trang admin xem trajectory
- [x] U3 Tool mới: `get_document`, `compare_documents`, `extract_structured` (`src/agents/doc_tools.py`; ACL như retrieval, không có quyền và không tồn tại trả cùng thông báo; giá trị trích xuất phải có câu trích nguyên văn trong tài liệu). Không thêm `propose_case`/`request_approval` riêng: `escalate_to_human` đã đi luồng đề xuất → người duyệt (U5a)
- [x] U4 Multi-step (code): planner `REACT_PLANNER=true` (1 lời gọi lập ≤6 bước + deliverable `answer|comparison_table|action_checklist`, nới ngân sách bước có trần `REACT_PLANNER_MAX_STEPS`); generate định dạng theo deliverable; frontend render bảng + checklist. Kịch bản dùng kho hiện có (so sánh chính sách, checklist hồ sơ); chưa thêm hợp đồng hư cấu. Chưa đo live
- [x] U5a HITL cho CREATE_CASE: thêm từ chối (`POST /chat/requests/{id}/ticket/reject`, có lý do, idempotent), đề xuất đã từ chối không xác nhận được nữa, duyệt/từ chối đều ghi `audit_logs`; nút "Không gửi" ở frontend
- [x] U5 Task state: LangGraph checkpointer (`src/agents/checkpoint.py`, `AGENT_CHECKPOINT_URL` = sqlite:/// local, postgresql:// production), thread = tenant:user:request_id. Retry cùng request_id: dừng giữa chừng thì chạy tiếp từ node cuối đã xong, đã xong thì trả lại kết quả (0 lời gọi LLM). Run log có `run_kind` fresh/resumed/replayed
- [ ] U5b Bật checkpoint trên Render (Postgres Supabase, cần user cho phép) + TTL dọn thread cũ; resume ở mức tool call trong react (hiện ở mức node: react lỗi giữa chừng thì chạy lại cả vòng react)
- [x] U6 Memory: hội thoại (history + condense, có sẵn) + task memory: backend gửi `previous_request_id` (lượt gần nhất đã trả lời trong cùng hội thoại), agent nạp chunk của lượt đó từ checkpoint cùng tenant+user, react dùng làm bằng chứng sẵn có. Memory dài hạn theo user: chưa làm, chờ số U7
- [ ] U7 Benchmark: bộ task gồm hỏi 1 bước, multi-hop, nhiều bước, hỏi tiếp nhiều lượt, hành động ghi; gold = kết quả + tool + tham số. Metric: task success, tool selection accuracy, argument accuracy, số bước, chất lượng trajectory, hallucination, p95 latency, chi phí/task. 4 nhánh: RAG thuần (retrieve → generate), fixed workflow (pipeline), ReAct, ReAct + memory. Tách dev/held-out

## Tiếp theo (lần lượt từ trên xuống)
- [ ] Có key LLM mới (FPT trả 401 từ 09/11) hoặc Gemini: `GEMINI_API_KEY` trong `.env` đang **rỗng** (11/11); kiểm tên model qua `/models`
- [ ] Chạy `scripts/reindex_collections.py`, rồi chạy lại eval_agent / eval_acl_e2e / eval_agent_trajectory (so redundant_searches/latency với số 09/11: 20 search thừa, p50 4,1 s), hiệu chỉnh ngưỡng retrieval/rerank cho Gemini
- [ ] Push 3 commit local (`b54771e`, `5257273`, `5d8b952`) khi user cho phép; trước đó chạy migration 0014 trên Supabase
- [ ] Thu hồi/đổi FPT key từng nằm trong `.env.example` (cả `.env` local và env Render)
- [ ] Sửa metadata Chroma của 33 chunk `13-QD-ABC` cho khớp registry
- [ ] Cập nhật baseline số chunk trong `tests/test_migration_parity.py`, `test_production_cutover_smoke.py` cho collection `_gemini` (4 test live fail 11/11)
- [ ] Held-out set mới (không còn câu active)
- [ ] Merge PR #1, chuyển các service Render sang `--branch main`
- [ ] Bỏ URL hardcode `DEMO_FRONTEND_ORIGIN` / `DEMO_AGENT_SERVICE_URL`, đặt bằng env qua Render API
