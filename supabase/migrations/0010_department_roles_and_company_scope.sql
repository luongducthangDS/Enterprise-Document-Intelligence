-- Simplify runtime roles and align direct-database defense-in-depth with FastAPI ACL.

create or replace function public.current_user_role()
returns text language sql security definer stable set search_path = public as $$
  select upper(role) from public.profiles where id = auth.uid()
$$;

create or replace function public.current_user_department()
returns text language sql security definer stable set search_path = public as $$
  select upper(department) from public.profiles where id = auth.uid()
$$;

create or replace function public.prevent_self_privilege_escalation()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  -- Trusted backend/migration connections do not carry a Supabase auth.uid().
  if auth.uid() is null or public.current_user_role() = 'SUPER_ADMIN' then
    return new;
  end if;
  if new.role is distinct from old.role
     or new.department is distinct from old.department
     or new.access_level is distinct from old.access_level
     or new.manager_id is distinct from old.manager_id then
    raise exception 'Không được tự đổi role/department/access_level/manager_id';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_prevent_self_privilege_escalation on public.profiles;
create trigger trg_prevent_self_privilege_escalation
  before update on public.profiles
  for each row execute function public.prevent_self_privilege_escalation();

alter table public.profiles drop constraint if exists profiles_role_check;

update public.profiles
set role = case upper(role)
  when 'SUPER_ADMIN' then 'SUPER_ADMIN'
  when 'ADMIN' then 'SUPER_ADMIN'
  when 'MANAGER' then 'DEPARTMENT_MANAGER'
  when 'HR_ADMIN' then 'DEPARTMENT_MANAGER'
  when 'DEPARTMENT_MANAGER' then 'DEPARTMENT_MANAGER'
  else 'EMPLOYEE'
end;

alter table public.profiles add constraint profiles_role_check
  check (role in ('EMPLOYEE', 'DEPARTMENT_MANAGER', 'SUPER_ADMIN'));

-- Profile access: users keep their existing own/report policies; only SUPER_ADMIN
-- receives cross-user read/update access.
drop policy if exists profiles_hr_admin_read on public.profiles;
drop policy if exists profiles_hr_admin_update on public.profiles;
drop policy if exists "hr_admin sees all profiles" on public.profiles;
drop policy if exists profiles_super_admin_read on public.profiles;
drop policy if exists profiles_super_admin_update on public.profiles;
create policy profiles_super_admin_read on public.profiles for select
  using (public.current_user_role() = 'SUPER_ADMIN');
create policy profiles_super_admin_update on public.profiles for update
  using (public.current_user_role() = 'SUPER_ADMIN')
  with check (public.current_user_role() = 'SUPER_ADMIN');

-- Replace permissive/legacy document policies with scope-aware ACL.
drop policy if exists documents_authenticated_read on public.documents;
drop policy if exists documents_hr_admin_write on public.documents;
drop policy if exists "authenticated read documents" on public.documents;
drop policy if exists "hr_admin delete documents" on public.documents;
drop policy if exists "hr_admin insert documents" on public.documents;
drop policy if exists "hr_admin update documents" on public.documents;
drop policy if exists documents_scoped_read on public.documents;
drop policy if exists documents_manager_write on public.documents;
create policy documents_scoped_read on public.documents for select to authenticated
  using (
    public.current_user_role() = 'SUPER_ADMIN'
    or (
      upper(coalesce(confidentiality, 'INTERNAL')) not in ('CONFIDENTIAL', 'RESTRICTED')
      and (
        access_scope = 'COMPANY_WIDE'
        or (access_scope = 'DEPARTMENT' and upper(department) = public.current_user_department())
        or (
          access_scope = 'ROLE'
          and upper(department) = public.current_user_department()
          and upper(authorized_role) = public.current_user_role()
        )
        or (access_scope = 'RESTRICTED' and owner_user_id = auth.uid())
      )
    )
  );
create policy documents_manager_write on public.documents for all
  using (
    public.current_user_role() = 'SUPER_ADMIN'
    or (
      public.current_user_role() = 'DEPARTMENT_MANAGER'
      and upper(department) = public.current_user_department()
    )
  )
  with check (
    public.current_user_role() = 'SUPER_ADMIN'
    or (
      public.current_user_role() = 'DEPARTMENT_MANAGER'
      and upper(department) = public.current_user_department()
      and access_scope in ('DEPARTMENT', 'RESTRICTED')
    )
  );

-- Retire legacy HR_ADMIN cross-user policies on the remaining tables.
drop policy if exists conversations_hr_admin_read on public.conversations;
drop policy if exists "hr_admin reads all conversations" on public.conversations;
drop policy if exists conversations_super_admin_read on public.conversations;
create policy conversations_super_admin_read on public.conversations for select
  using (public.current_user_role() = 'SUPER_ADMIN');

drop policy if exists messages_hr_admin_read on public.messages;
drop policy if exists "hr_admin reads all messages" on public.messages;
drop policy if exists messages_super_admin_read on public.messages;
create policy messages_super_admin_read on public.messages for select
  using (public.current_user_role() = 'SUPER_ADMIN');

drop policy if exists tickets_assignee_or_hr_admin on public.tickets;
drop policy if exists "assignee/hr_admin manage tickets" on public.tickets;
drop policy if exists tickets_assignee_or_super_admin on public.tickets;
create policy tickets_assignee_or_super_admin on public.tickets for all
  using (assignee_id = auth.uid() or public.current_user_role() = 'SUPER_ADMIN')
  with check (assignee_id = auth.uid() or public.current_user_role() = 'SUPER_ADMIN');

drop policy if exists chat_requests_hr_admin_read on public.chat_requests;
drop policy if exists chat_requests_super_admin_read on public.chat_requests;
create policy chat_requests_super_admin_read on public.chat_requests for select
  using (public.current_user_role() = 'SUPER_ADMIN');

drop policy if exists ingestion_jobs_hr_admin on public.ingestion_jobs;
drop policy if exists ingestion_jobs_super_admin on public.ingestion_jobs;
create policy ingestion_jobs_super_admin on public.ingestion_jobs for all
  using (public.current_user_role() = 'SUPER_ADMIN')
  with check (public.current_user_role() = 'SUPER_ADMIN');

drop policy if exists index_jobs_hr_admin on public.index_jobs;
drop policy if exists index_jobs_super_admin on public.index_jobs;
create policy index_jobs_super_admin on public.index_jobs for all
  using (public.current_user_role() = 'SUPER_ADMIN')
  with check (public.current_user_role() = 'SUPER_ADMIN');

drop policy if exists evaluation_runs_hr_admin on public.evaluation_runs;
drop policy if exists evaluation_runs_super_admin on public.evaluation_runs;
create policy evaluation_runs_super_admin on public.evaluation_runs for all
  using (public.current_user_role() = 'SUPER_ADMIN')
  with check (public.current_user_role() = 'SUPER_ADMIN');
