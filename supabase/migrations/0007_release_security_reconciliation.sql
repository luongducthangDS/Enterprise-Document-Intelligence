-- Idempotent reconciliation for projects that applied RLS before the three
-- worker tables and the profile privilege guard were added to the repository.

create or replace function public.current_user_role()
returns text
language sql
security definer
stable
set search_path = public
as $$
  select lower(role) from public.profiles where id = auth.uid()
$$;

alter table public.ingestion_jobs enable row level security;
alter table public.index_jobs enable row level security;
alter table public.evaluation_runs enable row level security;

drop policy if exists ingestion_jobs_hr_admin on public.ingestion_jobs;
create policy ingestion_jobs_hr_admin on public.ingestion_jobs for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');

drop policy if exists index_jobs_requester_read on public.index_jobs;
create policy index_jobs_requester_read on public.index_jobs for select
  using (requested_by = auth.uid());
drop policy if exists index_jobs_hr_admin on public.index_jobs;
create policy index_jobs_hr_admin on public.index_jobs for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');

drop policy if exists evaluation_runs_requester_read on public.evaluation_runs;
create policy evaluation_runs_requester_read on public.evaluation_runs for select
  using (requested_by = auth.uid());
drop policy if exists evaluation_runs_hr_admin on public.evaluation_runs;
create policy evaluation_runs_hr_admin on public.evaluation_runs for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');

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
