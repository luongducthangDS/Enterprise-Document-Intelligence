-- Initial schema: profiles (users/RBAC), conversations, messages, tickets, documents.
-- Vector embeddings KHÔNG ở đây — sống ở Chroma Cloud (src/ingestion/indexer.py).
-- Chạy 1 lần qua Supabase SQL Editor (Dashboard > SQL Editor > New query > Run).

-- ============================================================
-- 1. profiles — mở rộng auth.users (Supabase Auth có sẵn), không tự làm bảng password
-- ============================================================
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  role text not null check (role in ('employee','manager','hr_admin')),
  employment_status text not null default 'full_time'
    check (employment_status in ('probation','full_time','on_notice_termination','resigned')),
  department text,
  business_unit text,
  contract_type text check (contract_type in ('xac_dinh_thoi_han','khong_xac_dinh_thoi_han','thu_viec')),
  tenure_months integer default 0,
  seniority_years integer default 0,
  access_level text not null default 'self_only'
    check (access_level in ('self_only','team_scope','org_wide')),
  manager_id uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ============================================================
-- 2. conversations + messages
-- ============================================================
create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  citations jsonb not null default '[]',
  confidence_score numeric(4,3),
  escalated boolean not null default false,
  ticket_id uuid,
  created_at timestamptz not null default now()
);

-- ============================================================
-- 3. tickets — đúng theo data/metadata/ticket_routing_rules.json::ticket_template
-- ============================================================
create table public.tickets (
  id uuid primary key default gen_random_uuid(),
  ticket_code text unique not null,
  conversation_id uuid references public.conversations(id),
  message_id uuid references public.messages(id),
  requester_id uuid not null references public.profiles(id),
  employee_question text not null,
  escalate_reason text not null
    check (escalate_reason in ('low_confidence','out_of_scope','personal_data_required','user_requested_human')),
  confidence_score numeric(4,3),
  category text,
  target_department text not null check (target_department in ('CB','ER','TA','LD','HRBP')),
  priority text not null check (priority in ('Low','Medium','High')),
  status text not null default 'open' check (status in ('open','in_progress','resolved','closed')),
  assignee_id uuid references public.profiles(id),
  resolution_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz
);

alter table public.messages
  add constraint messages_ticket_id_fkey foreign key (ticket_id) references public.tickets(id);

-- ============================================================
-- 4. documents — mirror data/metadata/document_registry.csv
-- ============================================================
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  source_file text unique not null,
  category text not null,
  status text not null default 'raw'
    check (status in ('raw','processed','processed_incomplete','rejected')),
  source_type text not null
    check (source_type in ('government_law','official_policy','public_template','synthetic','public_article','eval_asset','config','rejected')),
  is_official_policy boolean not null default false,
  caveat text,
  processed_path text,
  chunks_path text,
  chroma_indexed_at timestamptz,
  uploaded_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ============================================================
-- 5. RLS — bật cho cả 5 bảng + policy theo role/ownership
-- ============================================================
alter table public.profiles enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.tickets enable row level security;
alter table public.documents enable row level security;

-- profiles
create policy "own profile" on public.profiles for select
  using (id = auth.uid());
create policy "manager sees reports" on public.profiles for select
  using (manager_id = auth.uid());
create policy "hr_admin sees all profiles" on public.profiles for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin'));
create policy "user updates own profile" on public.profiles for update
  using (id = auth.uid());

-- conversations
create policy "own conversations" on public.conversations for all
  using (user_id = auth.uid());
create policy "hr_admin reads all conversations" on public.conversations for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin'));

-- messages (quyền dựa theo conversation cha)
create policy "own messages" on public.messages for all
  using (exists (
    select 1 from public.conversations c
    where c.id = messages.conversation_id and c.user_id = auth.uid()
  ));
create policy "hr_admin reads all messages" on public.messages for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin'));

-- tickets
create policy "requester reads own tickets" on public.tickets for select
  using (requester_id = auth.uid());
create policy "assignee/hr_admin manage tickets" on public.tickets for all
  using (
    assignee_id = auth.uid()
    or exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin')
  );

-- documents
create policy "authenticated read documents" on public.documents for select
  using (auth.role() = 'authenticated');
create policy "hr_admin insert documents" on public.documents for insert
  with check (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin'));
create policy "hr_admin update documents" on public.documents for update
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin'));
create policy "hr_admin delete documents" on public.documents for delete
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'hr_admin'));
