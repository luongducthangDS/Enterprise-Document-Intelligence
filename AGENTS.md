# AGENTS.md

P-153 Enterprise Document Intelligence Agent: hỏi đáp tài liệu nội bộ đa phòng ban có trích dẫn, ACL fail-closed, LangGraph agent (pipeline hoặc react gọi tool), MCP server. Log phiên cũ: `logs/Codex-archive-2026-08.md`.

Đọc trước khi làm: [docs/RULES.md](docs/RULES.md) > [docs/PRD.md](docs/PRD.md) > [ARCHITECTURE](docs/ARCHITECTURE.md), [DESIGN](docs/DESIGN.md), [TASKS](docs/TASKS.md), [PROGRESS](docs/PROGRESS.md).

## Trạng thái (2026-11-11)
- Demo public chạy `AGENT_MODE=react` (https://enterprise-document-intelligence-unh1.onrender.com). 3 commit local chưa push trên `feat/recruiter-demo-deploy`; push kích hoạt deploy, cần user cho phép và chạy migration 0014 trước.
- FPT key 401 từ 09/11: agent demo và eval live đang hỏng tới khi có key mới. Chi tiết và số đo ở `docs/PROGRESS.md`.
- Việc tiếp theo: mục đầu tiên chưa tick trong `docs/TASKS.md`.

## Gotchas
- Render CLI không sửa env của service có sẵn; dùng REST API `PUT /v1/services/{id}/env-vars/{key}` với token trong `~/.render/cli.yaml`. Quay về pipeline: đặt `AGENT_MODE=pipeline` rồi deploy lại.
- Service `p-153-agent` cũ (branch main, 21/10) gọi OpenAI với key lỗi; demo không phụ thuộc nó.
- Vercel team `marzo` từ chối tạo project (403), nên frontend ở Render Static Site.
- Test giả lập `agent.astream` phải yield `("updates", step)` (SSE dùng `stream_mode=["updates","custom"]`).
- Gemini không nhận `chat_template_kwargs`; tắt thinking bằng `reasoning_effort=none` (chỉ dòng flash). Gemini không có `/rerank`.
- Đã thêm `*.zip` vào `.gitignore`.
