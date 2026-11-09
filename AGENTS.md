# AGENTS.md
Log chi tiết các phiên trước lưu ở logs/Codex-archive-2026-08.md

## Trạng thái hiện tại
- Đã thêm *.zip vào .gitignore.

## 2026-11-09 — Chế độ tool-calling agent và MCP server (chưa commit)
- `AGENT_MODE=react` (mặc định `pipeline`): node `react` trong `src/agents/nodes/react.py` thay knowledge_lookup/retrieve/grade/rewrite. LLM (router_model, DeepSeek-V4-Flash) gọi tool `search_policies`, `lookup_structured_policy`, `escalate_to_human`, tối đa `REACT_MAX_STEPS`=4 vòng; sau đó vào generate/confidence/hallucination/finalize như cũ. Lỗi LLM hoặc không gọi tool thì search 1 lần bằng câu gốc.
- `fpt_client._post_chat_completion` có thêm tham số `tools`. Đã kiểm 09/11: GLM-5.2 và DeepSeek-V4-Flash trên FPT đều trả `tool_calls` chuẩn OpenAI.
- MCP: `src/mcp_server.py` (mcp 2.x, `MCPServer`, không phải FastMCP), tool `ask_documents`, cấu hình `.mcp.json`. Danh tính lấy từ env `MCP_*`. Log của agent bị đẩy sang stderr vì stdout là kênh giao thức.
- Đã kiểm: `tests/test_agents/test_react_agent.py`; toàn bộ `tests/` (trừ e2e) 609 passed. MCP client stdio gọi được, có trích dẫn.
- Eval 09/11, `qa_eval_set` (68 câu active, judge LLM; `eval/results/agent_eval_{pipeline,react}_20261109.json`): in_scope pass 33/67 → 41/67 (49% → 61%); so theo cặp react thắng 9 câu, thua 1 câu (qa_029); context_found 39 → 45, answer_correct 34 → 43, escalate oan 18 → 13. Đổi lại p50 2,0 s → 5,8 s, p95 6,8 s → 14,8 s (backend chờ agent 120 s nên không bị timeout).
- `eval/scripts/eval_agent.py` đã hỏng từ khi bắt buộc identity (mọi câu lỗi `Missing authenticated identity fields`). Đã sửa: truyền identity EXECUTIVE/ADMIN như eval_retrieval/eval_guardrail. Số cũ trong `agent_eval_report.json` không so sánh được với số mới.
- Còn lại: `escalate_to_human` chỉ map về `personal_data_required` hoặc `low_confidence` vì `escalate_reason` là Literal. Latency tăng khoảng 3–4 s; nếu cần nhanh hơn, giảm `REACT_MAX_STEPS`.

## 2026-11-05 — Bản demo public cho nhà tuyển dụng
Live: https://enterprise-document-intelligence-unh1.onrender.com (không cần đăng nhập, chọn vai trò HR/Product/Accounting).

Hạ tầng (Render workspace `My Workspace`, tất cả plan free, region Singapore):
- Frontend: static site `enterprise-document-intelligence` (`srv-dbm0qnl9fdbs73bg24jg`).
- Backend: `p-153-backend` (`srv-dbm0qjg8v5cc73d7bck0`), `DEMO_MODE=true`.
- Agent: `p-153-agent-demo` (`srv-dbm0u3lbedkc73askteg`), dùng FPT + Chroma Cloud.
- DB: Supabase `enterprise-document-intelligence` (ref `hpnsijxrkfcxrzkwinym`), đã chạy migration 0001-0013 và seed. App kết nối bằng role `app_backend` qua pooler `aws-0-ap-southeast-1`; `DATABASE_URL` nằm trong `.env`.

Thiết kế demo:
- `POST /auth/demo` tạo user EMPLOYEE tạm cho từng khách; chat giới hạn 30 lượt/IP/giờ, 300 lượt/ngày (đếm trong RAM, reset khi restart).
- Quyền admin, kho tài liệu và upload không mở ra public.

Gotcha:
- Render CLI không sửa được env của service có sẵn. Vì vậy `backend/main.py` (`DEMO_FRONTEND_ORIGIN`) và `backend/app/core/config.py` (`DEMO_AGENT_SERVICE_URL`) hardcode URL khi `DEMO_MODE` bật. Sửa env trên dashboard thì bỏ được hai hằng này.
- Service `p-153-agent` cũ (branch main, deploy 21/10) gọi OpenAI với key lỗi nên không dùng được; bản demo không phụ thuộc nó.
- Vercel team `marzo` từ chối tạo project (403), nên frontend ở Render Static Site.
- Bảng `documents` rỗng và không có file gốc (Cloudinary không truy cập được): trích dẫn chỉ hiện đoạn trích, không mở được PDF/DOCX gốc.

Còn lại:
- PR #1 chưa merge; các service đang deploy từ branch `feat/recruiter-demo-deploy`. Sau khi merge, chuyển `--branch main`.
- `.env.example` trong working tree đang chứa một FPT key thật: không commit, nên thu hồi key.
- Mật khẩu demo cũ từng nằm trong `LoginView.tsx` và còn trong lịch sử git của repo public.
