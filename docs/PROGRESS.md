# Progress

Log chi tiết các phiên cũ: `logs/Codex-archive-2026-08.md`, `WORKLOG.md`, `JOURNAL.md`.

## Trạng thái (2026-11-11)
Nhánh `feat/recruiter-demo-deploy`, ahead 3 so với origin (`b54771e`, `5257273`, `5d8b952` chưa push; push sẽ kích hoạt deploy). Working tree có thay đổi QE chưa commit của session khác (TESTING.md, EVAL_SPEC.md, eval scripts, tests, dataset candidates).

### Demo public (05/11)
https://enterprise-document-intelligence-unh1.onrender.com: không cần đăng nhập, chọn vai trò. Render free, Singapore: frontend static `enterprise-document-intelligence`, backend `p-153-backend` (`DEMO_MODE=true`), agent `p-153-agent-demo` (FPT + Chroma Cloud, `AGENT_MODE=react`). DB Supabase `enterprise-document-intelligence`, migration 0001–0013 + seed, role `app_backend` qua pooler. `POST /auth/demo` tạo user EMPLOYEE tạm; giới hạn 30 lượt/IP/giờ, 300 lượt/ngày (RAM).

### Agent react + MCP (09/11)
- LLM (router_model, DeepSeek-V4-Flash) gọi `search_policies`, `lookup_structured_policy`, `escalate_to_human`, `calculate_annual_leave`, tối đa 4 vòng; lỗi LLM hoặc không gọi tool thì search 1 lần bằng câu gốc.
- MCP `ask_documents` đã kiểm bằng client stdio; chưa thử trong Claude Desktop/Code thật.
- Vá ACL: 33 chunk `13-QD-ABC_...` mang `RUNTIME_UPLOAD` + `COMPANY_WIDE` trong khi registry ghi Accounting → HR/Product/Ops đọc được. Code đã chặn (registry quyết định); metadata Chroma chưa sửa.
- Schema: thêm `hallucination_detected`, `requires_live_accounting_erp_data` vào `EscalateReason`.

### Số đo 09/11 (`eval/results/*_20261109.json`)
- qa_eval_set in-scope: pipeline 33/67, react 43/67 (thắng 10, thua 0); p50 2,0 → 4,9 s, p95 6,8 → 13,6 s.
- ACL e2e: trước vá pipeline 11/15, react 9/15; sau vá 15/15 cả hai. Type-C 27/30 cả hai (canonical 20/20). Guardrail pilot 14/14.
- Trajectory (react): tool 10/10, 3,3 LLM call/câu, gold 47/67 (6 nhờ tìm lại), 20 search thừa. Bản pipeline lỗi 401 nên chưa có số so sánh chi phí.

### Gemini (code xong, chưa chạy thật)
`LLM_PROVIDER=gemini`: agent `gemini-2.5-flash`, router/hallucination `-flash-lite`, judge `-pro`; rerank bằng LLM; embedding `gemini-embedding-001` 768 chiều; collection `<tên>_gemini`.

### Nâng cấp agentic (11/11, 15 commit local chưa push, chưa đo đủ live)
Kế hoạch và trạng thái từng mục ở `TASKS.md` (U0–U7). Đã có code + test (637 test agent, 166 test backend pass):
- Tool registry có schema pydantic (lỗi tham số trả về cho model), timeout + lỗi tool có cấu trúc; MCP thêm `search_policies`.
- Tool mới `get_document`, `compare_documents`, `extract_structured` (ACL như retrieval; giá trị trích phải có câu trích nguyên văn).
- Planner `REACT_PLANNER` + kết quả dạng bảng so sánh / checklist (frontend render bảng và checkbox).
- Run log mỗi lần chạy (trajectory, args, latency, lỗi, retry, token, chi phí); nội dung chỉ khi `RUN_LOG_CONTENT=true`, đã che PII.
- HITL: từ chối đề xuất case + audit log cho duyệt/từ chối.
- Checkpointer `AGENT_CHECKPOINT_URL`: retry cùng request_id thành resume/replay; task memory giữa các lượt qua `previous_request_id`.
- Benchmark 24 task × 5 nhánh (`eval/scripts/eval_agent_benchmark.py`). Chưa có số đủ bộ: quota Gemini free.
- Đo được tới giờ (smoke 2 task, không đủ để kết luận): router `flash-lite` xếp sai câu chính sách, đổi sang `flash` thì đúng.

### Sự cố 11/11
`src/`, `tests/`, `scripts/`, `supabase/`, `presentation/` (220 file tracked) biến mất khỏi đĩa khi thư mục 01-ai-engineering được sắp xếp lại; đã khôi phục từ HEAD bằng `git checkout`. Thay đổi chưa commit trong các thư mục đó (nếu có) không khôi phục được; transcript không cho thấy file nào bị thiếu.

## Hỏng / rủi ro
- `.env` dùng key Gemini số 2 của DocuMind (key 1 không còn dùng được dòng 2.5). Gói free chỉ vài chục request/ngày/model: hết quota thì eval lỗi 429 PerDay. Index Gemini chỉ có ở Chroma local trong scratchpad của session 11/11 (Cloud chưa index, collection `_gemini` rỗng).
- `backend/tests/test_conversations.py::test_get_conversation_messages_endpoint` flaky (2 message cùng `created_at`).
- 4 test live (Chroma Cloud) fail vì baseline số chunk hard-code cho collection cũ.
- FPT key trả 401 "Invalid API Key" từ 09/11: demo agent và mọi eval live cần key mới.
- Một FPT key thật từng nằm trong `.env.example` (đã xoá khỏi working tree), key cũng có trong env Render: phải đổi ở cả hai nơi.
- Mật khẩu demo cũ còn trong lịch sử git của repo public (`LoginView.tsx`).
- Bảng `documents` rỗng, file gốc trên Cloudinary không truy cập được: trích dẫn chỉ hiện đoạn trích.

## Bước tiếp theo
Mục đầu tiên chưa tick trong `TASKS.md` (cần key LLM).
