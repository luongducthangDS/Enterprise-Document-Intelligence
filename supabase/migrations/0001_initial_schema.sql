-- Canonical backend schema for the custom-JWT architecture.
-- Vector embeddings live in Chroma; PostgreSQL stores identity, chat, tickets,
-- documents and durable background-job state.

create extension if not exists pgcrypto;

create table public.users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  hashed_password text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index users_email_idx on public.users (email);

create table public.profiles (
  id uuid primary key references public.users(id) on delete cascade,
  display_name text not null default '',
  role text not null default 'employee',
  employment_status text not null default 'full_time',
  department text,
  business_unit text,
  contract_type text,
  tenure_months integer not null default 0,
  seniority_years integer not null default 0,
  access_level text not null default 'self_only',
  manager_id uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  state text not null default 'ACTIVE',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  ended_at timestamptz
);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  title text not null default 'Tài liệu không tên',
  source_file text unique not null,
  category text not null default 'GENERAL',
  version text,
  effective_date text,
  confidentiality text not null default 'INTERNAL',
  status text not null default 'ACTIVE',
  source_type text not null default 'FILE_UPLOAD',
  is_official_policy boolean not null default false,
  caveat text,
  processed_path text,
  chunks_path text,
  chroma_indexed_at timestamptz,
  uploaded_by uuid references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Cyclic references messages <-> tickets/chat_requests are added after all
-- three tables exist.
create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  role text not null,
  content text not null,
  chat_request_id uuid,
  citations jsonb not null default '[]'::jsonb,
  confidence_score numeric(4,3),
  escalated boolean not null default false,
  ticket_id uuid,
  created_at timestamptz not null default now()
);

create table public.tickets (
  id uuid primary key default gen_random_uuid(),
  ticket_code text unique not null,
  conversation_id uuid references public.conversations(id) on delete cascade,
  message_id uuid references public.messages(id) on delete cascade,
  requester_id uuid not null references public.profiles(id) on delete cascade,
  employee_question text not null,
  escalate_reason text not null,
  confidence_score numeric(4,3),
  category text,
  target_department text not null,
  priority text not null default 'Medium',
  status text not null default 'open',
  assignee_id uuid references public.profiles(id),
  resolution_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index tickets_ticket_code_idx on public.tickets (ticket_code);

create table public.chat_requests (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  question text not null,
  state text not null default 'QUEUED',
  answer_status text,
  answer text,
  citations jsonb,
  warnings jsonb,
  clarification jsonb,
  failure jsonb,
  user_message_id uuid references public.messages(id) on delete set null,
  assistant_message_id uuid references public.messages(id) on delete set null,
  parent_chat_request_id uuid references public.chat_requests(id) on delete set null,
  retry_count integer not null default 0,
  retryable boolean not null default false,
  latency_ms integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.messages
  add constraint messages_chat_request_id_fkey
    foreign key (chat_request_id) references public.chat_requests(id) on delete set null,
  add constraint messages_ticket_id_fkey
    foreign key (ticket_id) references public.tickets(id) on delete set null;

create table public.ingestion_jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  state text not null default 'QUEUED',
  stage text not null default 'UPLOADED',
  progress_percent integer not null default 0,
  chunk_count integer not null default 0,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.index_jobs (
  id uuid primary key default gen_random_uuid(),
  requested_by uuid not null references public.profiles(id) on delete cascade,
  document_ids jsonb,
  strategy text not null default 'REPLACE',
  state text not null default 'QUEUED',
  stage text not null default 'QUEUED',
  progress_percent integer not null default 0,
  active_index_version text not null default 'v1.0',
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.evaluation_runs (
  id uuid primary key default gen_random_uuid(),
  dataset_id text not null,
  index_version text,
  model_config_id text,
  requested_by uuid not null references public.profiles(id) on delete cascade,
  state text not null default 'QUEUED',
  stage text not null default 'QUEUED',
  progress_percent integer not null default 0,
  metrics jsonb,
  quality_gate text not null default 'PENDING',
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index conversations_user_id_idx on public.conversations (user_id);
create index messages_conversation_id_idx on public.messages (conversation_id);
create index chat_requests_conversation_id_idx on public.chat_requests (conversation_id);
create index chat_requests_user_id_idx on public.chat_requests (user_id);
create index ingestion_jobs_document_id_idx on public.ingestion_jobs (document_id);
create index index_jobs_requested_by_idx on public.index_jobs (requested_by);
create index evaluation_runs_requested_by_idx on public.evaluation_runs (requested_by);

