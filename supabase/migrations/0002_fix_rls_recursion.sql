-- Fix: infinite recursion trong RLS policy của profiles. Policy "hr_admin sees
-- all profiles" tự query lại public.profiles để kiểm tra role — Postgres phải
-- áp RLS cho chính subquery đó, kích hoạt lại policy này, đệ quy vô hạn. Lỗi
-- này còn lan sang mọi policy ở bảng khác (conversations/messages/tickets/
-- documents) có kiểm tra role qua profiles, vì chúng cũng phải trigger RLS của
-- profiles khi subquery.
--
-- Cách sửa chuẩn của Postgres/Supabase: dùng hàm SECURITY DEFINER để lấy role,
-- hàm này chạy với quyền của owner (bỏ qua RLS) nên không đệ quy.
--
-- Chạy qua Supabase SQL Editor SAU khi đã chạy 0001_initial_schema.sql.

create or replace function public.current_user_role()
returns text
language sql
security definer
stable
set search_path = public
as $$
  select role from public.profiles where id = auth.uid()
$$;

drop policy if exists "hr_admin sees all profiles" on public.profiles;
create policy "hr_admin sees all profiles" on public.profiles for select
  using (public.current_user_role() = 'hr_admin');

drop policy if exists "hr_admin reads all conversations" on public.conversations;
create policy "hr_admin reads all conversations" on public.conversations for select
  using (public.current_user_role() = 'hr_admin');

drop policy if exists "hr_admin reads all messages" on public.messages;
create policy "hr_admin reads all messages" on public.messages for select
  using (public.current_user_role() = 'hr_admin');

drop policy if exists "assignee/hr_admin manage tickets" on public.tickets;
create policy "assignee/hr_admin manage tickets" on public.tickets for all
  using (
    assignee_id = auth.uid()
    or public.current_user_role() = 'hr_admin'
  );

drop policy if exists "hr_admin insert documents" on public.documents;
create policy "hr_admin insert documents" on public.documents for insert
  with check (public.current_user_role() = 'hr_admin');

drop policy if exists "hr_admin update documents" on public.documents;
create policy "hr_admin update documents" on public.documents for update
  using (public.current_user_role() = 'hr_admin');

drop policy if exists "hr_admin delete documents" on public.documents;
create policy "hr_admin delete documents" on public.documents for delete
  using (public.current_user_role() = 'hr_admin');
