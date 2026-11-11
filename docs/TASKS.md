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
- [ ] U2 Observability: mỗi lần chạy lưu 1 bản ghi (input, output, trajectory, tool + args + kết quả, token, latency từng bước, lỗi/retry, chi phí ước tính theo bảng giá) ra JSONL local và bảng Supabase `agent_runs` (migration mới); trang admin xem được
- [ ] U3 Tool mới: `get_document` (đọc cả tài liệu, có ACL), `compare_documents`, `extract_structured` (ra JSON theo schema), `propose_case` (chỉ đề xuất), `request_approval`
- [ ] U4 Multi-step: planner lập danh sách bước, executor ReAct chạy từng bước, kết quả cuối là sản phẩm (bảng so sánh, danh sách việc), không chỉ câu trả lời. Kho hiện không có hợp đồng: thêm bộ hợp đồng NCC hư cấu có ngày hết hạn (đánh dấu synthetic), hoặc dùng `expiry_date` trong registry
- [ ] U5 Task state + HITL: LangGraph checkpointer (Postgres trên Supabase, SQLite khi test); `interrupt()` trước mọi tool ghi; API approve / reject (kèm lý do) / resume theo `thread_id`; tool timeout hoặc agent lỗi thì resume từ bước cuối đã xong; mọi hành động ghi vào `audit_logs`
- [ ] U6 Memory: hội thoại (đã có history + condense) + task memory qua checkpointer; memory dài hạn theo user chỉ làm nếu benchmark U7 cho thấy có lợi
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
