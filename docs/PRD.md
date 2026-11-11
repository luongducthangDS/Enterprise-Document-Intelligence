# PRD: P-153 Enterprise Document Intelligence Agent

Bản đầy đủ: [SYSTEM_SPECIFICATION_AND_DESIGN.md](SYSTEM_SPECIFICATION_AND_DESIGN.md) (mục 1–4, 12) và [README](../README.md) mục 2. File này là tóm tắt; khi lệch nhau thì bản đặc tả thắng.

## Bài toán
Trợ lý tri thức nội bộ đa phòng ban (HR, Accounting, Product, toàn công ty): nạp và kiểm duyệt tài liệu, hỏi đáp có dẫn nguồn (trang/sheet, mục, phiên bản, ngày hiệu lực), phân quyền theo phòng ban, quản lý phiên bản, chuyển người khi không đủ căn cứ.

## Người dùng
`EMPLOYEE`, `DEPARTMENT_MANAGER`, `SUPER_ADMIN`; khách xem demo public (vai trò tạm HR/Product/Accounting); nhà tuyển dụng (bản demo 05/11). Sản phẩm 6 tuần của chương trình AI Engineer (theo ghi chú của user).

## Mục tiêu
1. Hỏi đáp nhiều lượt (polling/SSE) với hybrid retrieval + rerank, trích dẫn mở được tài liệu gốc.
2. ACL phòng ban và tenant isolation fail-closed; không rò rỉ tài liệu khác phòng.
3. Guardrail: confidence/hallucination, từ chối và escalation có lý do.
4. Chế độ agent gọi tool (`AGENT_MODE=react`) và MCP server, đo bằng eval có trajectory.
5. Hành động ghi (CREATE_CASE) chỉ khi người dùng xác nhận.

## Không làm
Xem đặc tả mục 12 (giả định và giới hạn bàn giao). Demo public không mở quyền admin, kho tài liệu, upload.
