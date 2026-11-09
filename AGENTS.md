# AGENTS.md
Log chi tiết các phiên trước lưu ở logs/Codex-archive-2026-08.md

## Trạng thái hiện tại
- Đã thêm *.zip vào .gitignore.

## 2026-11-09 — Tool-calling agent, MCP server, vá rò rỉ ACL (đang chạy trên demo)
- **Chế độ agent:** `AGENT_MODE=react` (mặc định `pipeline`). Node `react` (`src/agents/nodes/react.py`) thay knowledge_lookup/retrieve/grade/rewrite; LLM (router_model, DeepSeek-V4-Flash) gọi `search_policies`, `lookup_structured_policy`, `escalate_to_human`, tối đa `REACT_MAX_STEPS`=4 vòng, rồi vào generate/confidence/hallucination/finalize như cũ. `escalate_to_human(missing_evidence)` khi đã có chunk chỉ dừng vòng tool (sửa qa_029). Lỗi LLM hoặc không gọi tool thì search 1 lần bằng câu gốc. `fpt_client._post_chat_completion` có tham số `tools` (GLM-5.2 và DeepSeek trên FPT đều hỗ trợ).
- **SSE:** `astream_answer` dùng `stream_mode=["updates","custom"]`; react phát `status` cho từng tool call qua `get_stream_writer`. Backend/frontend không cần sửa (đã hiển thị `status`). Test giả lập `agent.astream` phải yield `("updates", step)`.
- **MCP:** `src/mcp_server.py` (mcp 2.x, `MCPServer`), tool `ask_documents`, `.mcp.json`. Danh tính từ env `MCP_*`; log agent đẩy sang stderr. Đã kiểm bằng MCP client stdio; chưa thử trong Claude Desktop/Code thật (máy không có `claude` CLI trên PATH).
- **Vá ACL (lỗi có từ trước, cả pipeline):** 33 chunk `13-QD-ABC_...` trong Chroma `accounting_documents` mang `RUNTIME_UPLOAD` + `COMPANY_WIDE`, registry ghi `DEPARTMENT/ACCOUNTING` → nhân viên HR/Product/Operations đọc được. Sửa `runtime_upload_metadata_allowed`: file có trong registry thì registry quyết định (`registered_source_files`, registry cache theo mtime). Metadata trong Chroma vẫn sai, chưa sửa dữ liệu; code đã chặn.
- **Schema:** thêm `hallucination_detected`, `requires_live_accounting_erp_data` vào `EscalateReason` và map ABSTAIN (trước đó AgentAnswer ném ValidationError ở hai nhánh từ chối này).
- **Eval sửa/thêm:** `eval_agent.py` và `eval_type_c_contract.py` đã hỏng từ khi bắt buộc identity, nay truyền EXECUTIVE/ADMIN. Mới: `eval/scripts/eval_acl_e2e.py` (ACL qua agent thật; suite `acl` của eval_enterprise_suite chỉ gọi engine nên không bắt được lỗi trên).
- **Số đo 09/11** (`eval/results/*_20261109.json`): qa_eval_set in_scope pipeline 33/67, react_v2 43/67 (thắng 10, thua 0), p50 2,0 → 4,9 s, p95 6,8 → 13,6 s. ACL e2e trước vá: pipeline 11/15, react 9/15; sau vá 15/15 cả hai. Type-C 27/30 cả hai (canonical 20/20). Guardrail pilot 14/14 cả hai. qa_eval_set là dev set; held-out không còn câu active.
- **Render:** `p-153-agent-demo` có `AGENT_MODE=react`. Quay về: đặt env `AGENT_MODE=pipeline` qua API rồi deploy lại.
- **Còn lại:** thu hồi/đổi FPT key từng nằm trong `.env.example` (đã xoá khỏi working tree; key cũng nằm trong env Render nên phải đổi ở cả hai nơi). Sửa metadata Chroma của 13-QD-ABC cho khớp registry. Held-out set mới.

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
- Render CLI không sửa được env của service có sẵn, nhưng REST API (`PUT /v1/services/{id}/env-vars/{key}`) dùng được token trong `~/.render/cli.yaml`. Trước đây tưởng không sửa được env nên `backend/main.py` (`DEMO_FRONTEND_ORIGIN`) và `backend/app/core/config.py` (`DEMO_AGENT_SERVICE_URL`) hardcode URL khi `DEMO_MODE` bật. Giờ đặt env qua API là bỏ được hai hằng này.
- Service `p-153-agent` cũ (branch main, deploy 21/10) gọi OpenAI với key lỗi nên không dùng được; bản demo không phụ thuộc nó.
- Vercel team `marzo` từ chối tạo project (403), nên frontend ở Render Static Site.
- Bảng `documents` rỗng và không có file gốc (Cloudinary không truy cập được): trích dẫn chỉ hiện đoạn trích, không mở được PDF/DOCX gốc.

Còn lại:
- PR #1 chưa merge; các service đang deploy từ branch `feat/recruiter-demo-deploy`. Sau khi merge, chuyển `--branch main`.
- `.env.example` trong working tree đang chứa một FPT key thật: không commit, nên thu hồi key.
- Mật khẩu demo cũ từng nằm trong `LoginView.tsx` và còn trong lịch sử git của repo public.
