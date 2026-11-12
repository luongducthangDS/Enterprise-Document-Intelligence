-- CREATE_CASE có người duyệt: agent chỉ ĐỀ XUẤT ticket (PREFILL_DRAFT), Backend lưu
-- đề xuất ở đây; ticket chỉ được tạo khi người hỏi bấm xác nhận
-- (POST /chat/requests/{id}/ticket) và registry cho phép CREATE_CASE ở scenario đó.
-- Sau khi xác nhận, ticket_id/ticket_code được ghi vào cùng JSON để lần bấm sau
-- trả lại đúng ticket cũ (idempotent).
alter table public.chat_requests
  add column if not exists ticket_proposal jsonb;
