# AGENTS.md
Log chi tiết các phiên trước lưu ở logs/Codex-archive-2026-08.md

## Trạng thái hiện tại
- Đã thêm *.zip vào .gitignore.

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
