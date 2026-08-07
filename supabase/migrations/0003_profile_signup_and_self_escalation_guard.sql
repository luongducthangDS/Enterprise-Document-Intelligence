-- Fix 2 gap phát hiện khi review 0001/0002 (xem CLAUDE.md):
-- 1) profiles không có policy INSERT nào và không có trigger tạo profile khi
--    user đăng ký -> không có đường nào tạo được profile row từ client.
-- 2) Nếu chỉ đơn giản thêm policy "for insert/update using (id = auth.uid())"
--    thì user có thể tự set role/access_level/manager_id của chính mình khi
--    đăng ký hoặc khi update -> tự leo quyền lên 'hr_admin'. KHÔNG thêm policy
--    kiểu đó.
--
-- Giải pháp: tạo profile qua trigger AFTER INSERT trên auth.users (SECURITY
-- DEFINER, bỏ qua RLS), hardcode role='employee' + access_level='self_only'
-- (không đọc từ input do client kiểm soát) — cùng pattern chuẩn của Supabase.
-- User tự update các field vô hại (display_name/department/...) qua policy
-- "own profile" sẵn có; việc đổi role/access_level/manager_id bị chặn bởi
-- trigger BEFORE UPDATE trừ khi người thực hiện là hr_admin.
--
-- Chạy qua Supabase SQL Editor SAU khi đã chạy 0001 và 0002.

-- ============================================================
-- 1. Tự tạo profiles row khi có user mới đăng ký (auth.users)
-- ============================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name, role, access_level)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)),
    'employee',
    'self_only'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ============================================================
-- 2. Chặn tự leo quyền: non-hr_admin không được đổi role/access_level/
--    manager_id trên chính profile của mình (kể cả qua policy "own profile"
--    đang cho phép update hàng của chính mình ở mức row-level).
-- ============================================================
create or replace function public.prevent_self_privilege_escalation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if public.current_user_role() = 'hr_admin' then
    return new;
  end if;
  if new.role is distinct from old.role
     or new.access_level is distinct from old.access_level
     or new.manager_id is distinct from old.manager_id then
    raise exception 'Không được tự đổi role/access_level/manager_id của chính mình';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_prevent_self_privilege_escalation on public.profiles;
create trigger trg_prevent_self_privilege_escalation
  before update on public.profiles
  for each row execute function public.prevent_self_privilege_escalation();

-- ============================================================
-- 3. hr_admin cần policy update-any-row riêng — "own profile" ở 0001 chỉ cho
--    update hàng của chính mình, hr_admin không có cách nào sửa role/phòng
--    ban của người khác (vd promote lên manager) nếu thiếu policy này.
-- ============================================================
create policy "hr_admin updates any profile" on public.profiles for update
  using (public.current_user_role() = 'hr_admin');
