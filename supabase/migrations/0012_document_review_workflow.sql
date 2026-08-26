-- Quarantine workflow: uploaded documents are analysed in staging and only
-- become official knowledge after an explicit approval.

alter table public.documents
  add column if not exists content_type text,
  add column if not exists file_content bytea;

create table if not exists public.document_submissions (
  id uuid primary key default gen_random_uuid(),
  tenant text not null default 'nexatech',
  source_file text not null,
  content_type text,
  file_content bytea not null,
  title text not null,
  category text not null default 'GENERAL',
  department text not null,
  version text,
  effective_date text,
  confidentiality text not null default 'INTERNAL',
  access_scope text not null default 'RESTRICTED'
    check (access_scope in ('COMPANY_WIDE','DEPARTMENT','ROLE','RESTRICTED')),
  authorized_role text,
  status text not null default 'ANALYZING'
    check (status in (
      'ANALYZING','PENDING_REVIEW','APPROVING','PUBLISHING','PUBLISHED',
      'ANALYSIS_FAILED','PUBLISH_FAILED','CHANGES_REQUESTED','REJECTED'
    )),
  stage text not null default 'UPLOADED',
  progress_percent integer not null default 0 check (progress_percent between 0 and 100),
  extract_method text,
  extracted_text text,
  chunks jsonb not null default '[]'::jsonb,
  chunk_count integer not null default 0,
  analysis_warnings jsonb not null default '[]'::jsonb,
  error text,
  submitted_by uuid not null references public.profiles(id) on delete cascade,
  reviewed_by uuid references public.profiles(id) on delete set null,
  review_note text,
  reviewed_at timestamptz,
  published_document_id uuid references public.documents(id) on delete set null,
  publication_job_id uuid references public.ingestion_jobs(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (access_scope <> 'ROLE' or authorized_role is not null)
);

create index if not exists document_submissions_queue_idx
  on public.document_submissions (tenant, status, department, created_at desc);
create index if not exists document_submissions_submitter_idx
  on public.document_submissions (submitted_by, created_at desc);

alter table public.document_submissions enable row level security;

drop policy if exists document_submissions_scoped_read on public.document_submissions;
create policy document_submissions_scoped_read on public.document_submissions
  for select to authenticated using (
    submitted_by = auth.uid()
    or public.current_user_role() = 'SUPER_ADMIN'
    or (
      public.current_user_role() = 'DEPARTMENT_MANAGER'
      and upper(department) = public.current_user_department()
    )
  );

drop policy if exists document_submissions_manager_insert on public.document_submissions;
create policy document_submissions_manager_insert on public.document_submissions
  for insert to authenticated with check (
    submitted_by = auth.uid()
    and (
      public.current_user_role() = 'SUPER_ADMIN'
      or (
        public.current_user_role() = 'DEPARTMENT_MANAGER'
        and upper(department) = public.current_user_department()
      )
    )
  );

drop policy if exists document_submissions_manager_update on public.document_submissions;
create policy document_submissions_manager_update on public.document_submissions
  for update to authenticated using (
    public.current_user_role() = 'SUPER_ADMIN'
    or (
      public.current_user_role() = 'DEPARTMENT_MANAGER'
      and upper(department) = public.current_user_department()
    )
  ) with check (
    public.current_user_role() = 'SUPER_ADMIN'
    or (
      public.current_user_role() = 'DEPARTMENT_MANAGER'
      and upper(department) = public.current_user_department()
    )
  );
