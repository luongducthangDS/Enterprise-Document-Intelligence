create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  tenant text not null,
  actor_id uuid not null references public.profiles(id) on delete restrict,
  action text not null,
  resource_type text not null,
  resource_id text not null,
  before_state jsonb,
  after_state jsonb,
  created_at timestamptz not null default now()
);
create index if not exists audit_logs_tenant_created_idx on public.audit_logs (tenant, created_at desc);
create index if not exists audit_logs_resource_idx on public.audit_logs (tenant, resource_type, resource_id);
alter table public.audit_logs enable row level security;