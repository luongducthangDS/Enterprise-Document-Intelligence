-- A direct Supabase client may edit harmless fields in its own profile, but it
-- must never promote itself or change its reporting line.

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

