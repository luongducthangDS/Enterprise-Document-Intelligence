-- RLS is defense in depth for direct Supabase access. The v1 backend uses its
-- own JWT and a trusted database role; request authorization remains enforced
-- by FastAPI. Do not expose the backend database role to browser clients.

create or replace function public.current_user_role()
returns text
language sql
security definer
stable
set search_path = public
as $$
  select lower(role) from public.profiles where id = auth.uid()
$$;

alter table public.users enable row level security;
alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.tickets enable row level security;
alter table public.documents enable row level security;
alter table public.chat_requests enable row level security;
alter table public.ingestion_jobs enable row level security;
alter table public.index_jobs enable row level security;
alter table public.evaluation_runs enable row level security;

create policy profiles_read_own on public.profiles for select
  using (id = auth.uid());
create policy profiles_read_reports on public.profiles for select
  using (manager_id = auth.uid());
create policy profiles_hr_admin_read on public.profiles for select
  using (public.current_user_role() = 'hr_admin');
create policy profiles_update_own on public.profiles for update
  using (id = auth.uid());
create policy profiles_hr_admin_update on public.profiles for update
  using (public.current_user_role() = 'hr_admin');

create policy conversations_own on public.conversations for all
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy conversations_hr_admin_read on public.conversations for select
  using (public.current_user_role() = 'hr_admin');

create policy messages_own on public.messages for all
  using (exists (
    select 1 from public.conversations c
    where c.id = messages.conversation_id and c.user_id = auth.uid()
  ));
create policy messages_hr_admin_read on public.messages for select
  using (public.current_user_role() = 'hr_admin');

create policy tickets_requester_read on public.tickets for select
  using (requester_id = auth.uid());
create policy tickets_assignee_or_hr_admin on public.tickets for all
  using (assignee_id = auth.uid() or public.current_user_role() = 'hr_admin');

create policy documents_authenticated_read on public.documents for select
  to authenticated using (true);
create policy documents_hr_admin_write on public.documents for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');

create policy chat_requests_own on public.chat_requests for all
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy chat_requests_hr_admin_read on public.chat_requests for select
  using (public.current_user_role() = 'hr_admin');

create policy ingestion_jobs_hr_admin on public.ingestion_jobs for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');
create policy index_jobs_requester_read on public.index_jobs for select
  using (requested_by = auth.uid());
create policy index_jobs_hr_admin on public.index_jobs for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');
create policy evaluation_runs_requester_read on public.evaluation_runs for select
  using (requested_by = auth.uid());
create policy evaluation_runs_hr_admin on public.evaluation_runs for all
  using (public.current_user_role() = 'hr_admin')
  with check (public.current_user_role() = 'hr_admin');

