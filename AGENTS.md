# AGENTS.md

P-153 Enterprise Document Intelligence Agent: hỏi đáp tài liệu nội bộ đa phòng ban có trích dẫn, ACL fail-closed, LangGraph agent (pipeline hoặc react gọi tool), MCP server. Log phiên cũ: `logs/Codex-archive-2026-08.md`.

Đọc trước khi làm: [docs/RULES.md](docs/RULES.md) > [docs/PRD.md](docs/PRD.md) > [ARCHITECTURE](docs/ARCHITECTURE.md), [DESIGN](docs/DESIGN.md), [TASKS](docs/TASKS.md), [PROGRESS](docs/PROGRESS.md).

## Trạng thái (2026-11-11)
- Demo public (https://enterprise-document-intelligence-unh1.onrender.com) đã deploy `1c00c95` (11/11, cả 3 service live, migration 0014 đã chạy bằng role `app_backend`). **Chat vẫn FAILED** vì agent production còn dùng FPT (401); cần chuyển sang Gemini (index Cloud `_gemini` + env Render + key đủ quota).
- FPT key 401 từ 09/11: agent demo và eval live đang hỏng tới khi có key mới. Chi tiết và số đo ở `docs/PROGRESS.md`.
- 11/11: src/tests/scripts/supabase từng mất khỏi đĩa khi di chuyển thư mục, đã khôi phục từ git. Nâng cấp agentic U1–U7a đã có code (xem `docs/PROGRESS.md`), chưa có số benchmark đủ bộ vì quota Gemini free.
- Việc tiếp theo: mục đầu tiên chưa tick trong `docs/TASKS.md`.

## Gotchas
- Render CLI không sửa env của service có sẵn; dùng REST API `PUT /v1/services/{id}/env-vars/{key}` với token trong `~/.render/cli.yaml`. Quay về pipeline: đặt `AGENT_MODE=pipeline` rồi deploy lại.
- Service `p-153-agent` cũ (branch main, 21/10) gọi OpenAI với key lỗi; demo không phụ thuộc nó.
- Vercel team `marzo` từ chối tạo project (403), nên frontend ở Render Static Site.
- Test giả lập `agent.astream` phải yield `("updates", step)` (SSE dùng `stream_mode=["updates","custom"]`).
- Gemini không nhận `chat_template_kwargs`; tắt thinking bằng `reasoning_effort=none` (chỉ dòng flash). Gemini không có `/rerank`.
- Đã thêm `*.zip` vào `.gitignore`.
- Python `open()` ghi lại file sẽ đổi CRLF thành LF; git tự chuẩn hoá nên diff không nhiễu. Chuỗi tiếng Việt trong code có thể khác chuẩn Unicode (dựng sẵn/tổ hợp): sửa theo số dòng nếu so chuỗi không khớp.
- Eval Gemini: đặt `LLM_429_MAX_WAIT_S=60`, `VECTOR_DB_BACKEND=local` + `CHROMA_PERSIST_DIR` nếu Cloud chưa index `_gemini`; ghi stdout ra file thì thêm `PYTHONUNBUFFERED=1`.
