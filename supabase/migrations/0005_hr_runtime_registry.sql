-- ============================================================
-- Config tables cho canonical runtime registry (MVP-1, Workstream A Phase B)
--
-- Nguồn: docs/project/hr_physical_schema_and_knowledge_spec.md
--        docs/project/hr_interaction_boundary_plan.md
--          :: Runtime-Revised Canonical Scenario Registry
--
-- Migration này CHỈ THÊM bảng config mới, không sửa/không xoá bảng nào đang có.
-- Chưa chạy trên Supabase production — cần review gate theo spec trước.
--
-- CỐ Ý CHƯA LÀM trong file này:
-- * `messages`/`chat_requests` chưa được thêm cột boundary: `chat_requests`,
--   `ingestion_jobs`, `index_jobs`, `evaluation_runs` hiện KHÔNG có migration
--   nền trong repo dù SQLAlchemy model đã tồn tại. Phải reconcile phần đó
--   trước, nếu không migration này sẽ ALTER một bảng mà repo không định nghĩa.
-- * `hr_cases` và các bảng case khác là MVP-2, không nằm ở đây.
-- * Không có enum `CREATE_REQUEST`/`READ_STATUS`: runtime contract đã chuyển
--   hai action đó sang future integration.
-- ============================================================

create table if not exists public.hr_departments (
  id uuid primary key default gen_random_uuid(),
  code text unique not null
    check (code in ('HR_OPS','CB','HRBP','TA','LD','ER','FINANCE','LEGAL','IT','ADMIN','SAFETY')),
  name text not null,
  description text,
  default_contact_label text,
  sensitivity_cap text not null default 'High'
    check (sensitivity_cap in ('Low','Medium','High','Critical')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.hr_services (
  id uuid primary key default gen_random_uuid(),
  code text unique not null,
  name text not null,
  domain text not null,
  owner_department_id uuid not null references public.hr_departments(id),
  default_sla_hours integer check (default_sla_hours is null or default_sla_hours > 0),
  default_sensitivity text not null
    check (default_sensitivity in ('Low','Medium','High','Critical')),
  default_escalation_department_id uuid references public.hr_departments(id),
  runtime_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists hr_services_domain_idx on public.hr_services (domain);
create index if not exists hr_services_owner_idx on public.hr_services (owner_department_id);

create table if not exists public.scenarios (
  id integer primary key check (id between 1 and 64),
  service_id uuid not null references public.hr_services(id),
  name text not null,
  assistant_role text not null
    check (assistant_role in ('ANSWER','GUIDE','PREPARE_AND_HANDOFF','HUMAN_FIRST')),
  data_dependency text not null
    check (data_dependency in ('KNOWLEDGE_ONLY','EMPLOYEE_PROFILE','TRANSACTIONAL','MANAGER_DECISION','HR_CASE','EXTERNAL_SYSTEM')),
  runtime_source_status text not null
    check (runtime_source_status in ('IN_PRODUCT','SIMULATED_IN_PRODUCT','EXTERNAL_REAL','EXTERNAL_ASSUMED','HUMAN','KNOWLEDGE','NOT_AVAILABLE')),
  source_of_truth_label text not null,
  max_runtime_action text not null
    check (max_runtime_action in ('NONE','LINK_ONLY','PREFILL_DRAFT','CREATE_CASE')),
  final_owner_department_id uuid references public.hr_departments(id),
  final_owner_role text,
  sensitivity text not null check (sensitivity in ('Low','Medium','High','Critical')),
  mvp_phase text not null check (mvp_phase in ('MVP_1','MVP_2','FUTURE','OUT_OF_MVP')),
  runtime_behavior text not null,
  user_facing_action_label text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Owner phải xác định được: hoặc là phòng ban, hoặc là vai trò
  -- (Line Manager/Business leader/Hiring Manager), không được thiếu cả hai.
  constraint scenarios_owner_present
    check (final_owner_department_id is not null or final_owner_role is not null),
  -- Ranh giới đã chốt: CREATE_CASE chỉ dành cho administrative case trong
  -- allowlist MVP-2. Ràng buộc ở tầng DB để một lần seed sai không mở được
  -- quyền tạo case cho scenario nhạy cảm.
  constraint scenarios_create_case_allowlist
    check (max_runtime_action <> 'CREATE_CASE' or id in (13,17,20,27,28,45))
);

create index if not exists scenarios_phase_action_idx on public.scenarios (mvp_phase, max_runtime_action);
create index if not exists scenarios_role_dependency_idx on public.scenarios (assistant_role, data_dependency);
create index if not exists scenarios_service_idx on public.scenarios (service_id);
create index if not exists scenarios_sensitivity_idx on public.scenarios (sensitivity);

create table if not exists public.scenario_allowed_data_fields (
  id uuid primary key default gen_random_uuid(),
  scenario_id integer not null references public.scenarios(id) on delete cascade,
  field_key text not null,
  label text not null,
  required_for_prefill boolean not null default false,
  pii_class text not null check (pii_class in ('Low','Medium','High','Critical')),
  storage_policy text not null
    check (storage_policy in ('do_not_store','store_case_only','store_message_ok','store_metadata_only')),
  created_at timestamptz not null default now(),
  unique (scenario_id, field_key)
);

create index if not exists scenario_allowed_data_fields_scenario_idx
  on public.scenario_allowed_data_fields (scenario_id);
create index if not exists scenario_allowed_data_fields_required_idx
  on public.scenario_allowed_data_fields (required_for_prefill);

-- ============================================================
-- RLS — config đọc được cho mọi user đã đăng nhập, ghi chỉ qua service role
-- (Supabase service key bỏ qua RLS). Không mở policy write cho client.
-- ============================================================

alter table public.hr_departments enable row level security;
alter table public.hr_services enable row level security;
alter table public.scenarios enable row level security;
alter table public.scenario_allowed_data_fields enable row level security;

drop policy if exists hr_departments_read on public.hr_departments;
create policy hr_departments_read on public.hr_departments
  for select to authenticated using (true);

drop policy if exists hr_services_read on public.hr_services;
create policy hr_services_read on public.hr_services
  for select to authenticated using (true);

drop policy if exists scenarios_read on public.scenarios;
create policy scenarios_read on public.scenarios
  for select to authenticated using (true);

-- Allowed data fields lộ ra "assistant được hỏi gì" nên chỉ cần cho user đọc
-- scenario đang active; không có PII trong bảng này.
drop policy if exists scenario_allowed_data_fields_read on public.scenario_allowed_data_fields;
create policy scenario_allowed_data_fields_read on public.scenario_allowed_data_fields
  for select to authenticated using (true);
