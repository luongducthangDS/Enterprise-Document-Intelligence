# HR Physical Schema And Knowledge Specification

## Trạng thái

Tài liệu này là proposal sau khi business/data architecture đã freeze. Chưa viết migration, chưa mutate Supabase/Chroma, chưa code, chưa sinh content.

Source-of-truth nghiệp vụ duy nhất cho scenario runtime là `Runtime-Revised Canonical Scenario Registry` trong `docs/project/hr_interaction_boundary_plan.md`.

## Architecture Freeze

- `Runtime-Revised Canonical Scenario Registry` là source-of-truth duy nhất cho physical schema, seed data, boundary/router behavior và evaluation.
- `SIMULATED_IN_PRODUCT` chỉ là engineering metadata. UI không hiển thị "demo", "simulated", "synthetic".
- User-facing language dùng: "Chuẩn bị yêu cầu", "Bản nháp", "Hướng dẫn gửi", "Người phụ trách".
- Product không claim request đã submit hoặc external system đã tích hợp nếu chưa có thật.
- MVP-1 chỉ hỗ trợ `ANSWER`, `GUIDE`, `PREFILL_DRAFT`, `LINK_ONLY`.
- MVP-2 chỉ thêm controlled `CREATE_CASE` cho administrative cases ít nhạy cảm.
- `READ_STATUS` và direct `CREATE_REQUEST` là future integration.
- Sensitive ER/grievance trong MVP-1 chỉ human-first/link-only; chưa tạo confidential case khi chưa có ACL/audit/privacy model đầy đủ.

## Workstream A - Physical Data Design

### Auth Decision

Chốt target production dùng Supabase Auth:

- `auth.users` là identity source-of-truth.
- `public.profiles` là employee/profile business context và FK tới `auth.users(id)`.
- Không giữ `public.users` làm bảng auth production.
- SQLAlchemy model hiện có `UserDB(__tablename__="users")` phải được reconcile trước migration: hoặc bỏ khỏi production mapping, hoặc chỉ dùng cho local test adapter. Không để production vừa dùng `auth.users` vừa dùng `public.users`.

### Physical Schema Proposal

#### `profiles` - EXTEND existing

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Employee identity | PK, FK `auth.users(id)`, not null | primary key | self read; manager team read; HR scoped read | Supabase Auth | MVP_1 |
| `display_name` | Tên hiển thị | not null | text length guard | self/HR | Auth/profile | MVP_1 |
| `role` | App role | not null | enum `employee`, `manager`, `hr_admin`, future `hr_specialist` | admin update only | Access config | MVP_1 |
| `employment_status` | Context trả lời policy | not null | enum existing plus future values | self/HR | HRIS assumed/manual seed | MVP_1 |
| `department` | Department text tối thiểu | nullable | index if routing/filter needed | self/manager/HR | manual seed | MVP_1 |
| `business_unit` | BU text tối thiểu | nullable | optional index | self/manager/HR | manual seed | MVP_1 |
| `contract_type` | Applicability policy | nullable | enum existing | self/HR | manual seed | MVP_1 |
| `tenure_months` | Applicability rough context | not null default 0 | non-negative check | self/HR | manual seed | MVP_1 |
| `seniority_years` | Leave/benefit condition | not null default 0 | non-negative check | self/HR | manual seed | MVP_1 |
| `access_level` | Coarse RBAC | not null | enum `self_only`, `team_scope`, `org_wide` | admin update only | Access config | MVP_1 |
| `manager_id` | Reporting line tối thiểu | FK `profiles(id)`, nullable | index | manager/team RLS | manual seed | MVP_1 |
| `hr_department_id` | HR staff department membership | FK `hr_departments(id)`, nullable | index | HR admin manage | service config | MVP_2 |
| `created_at`, `updated_at` | Audit timestamps | not null | default now | system | DB | MVP_1 |

Relation hiện tại: giữ bảng `profiles`, thêm `hr_department_id` sau khi có `hr_departments`. Không tạo bảng `employee` riêng trong MVP để giảm migration.

#### `hr_departments` - NEW config

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Department id | PK | primary key | authenticated read; admin write | seed | MVP_1 |
| `code` | Stable code | not null | unique; enum-like seed `HR_OPS`, `CB`, `HRBP`, `TA`, `LD`, `ER`, `FINANCE`, `LEGAL`, `IT`, `ADMIN`, `SAFETY` | read | seed | MVP_1 |
| `name` | User-facing department name | not null | unique optional | read | seed | MVP_1 |
| `description` | Scope | nullable | none | read | seed | MVP_1 |
| `default_contact_label` | User-facing contact label | nullable | no fake URL | read | seed | MVP_1 |
| `sensitivity_cap` | Max sensitivity department can handle | not null | enum Low/Medium/High/Critical | admin write | security config | MVP_2 |
| `created_at`, `updated_at` | Timestamps | not null | default now | system | DB | MVP_1 |

#### `hr_services` - NEW config

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Service id | PK | primary key | read for authenticated; admin write | seed | MVP_1 |
| `code` | Stable service code | not null | unique; index | read | seed | MVP_1 |
| `name` | User-facing service name | not null | none | read | seed | MVP_1 |
| `domain` | Domain group | not null | index | read | registry | MVP_1 |
| `owner_department_id` | Primary accountable owner | FK `hr_departments(id)`, not null | index | read | operating model | MVP_1 |
| `default_sla_hours` | Baseline SLA | nullable | positive check | read | V-Nova baseline | MVP_1 |
| `default_sensitivity` | Default sensitivity | not null | enum Low/Medium/High/Critical | read | registry | MVP_1 |
| `default_escalation_department_id` | Escalation target | FK nullable | index | read | operating model | MVP_1 |
| `runtime_enabled` | Service visible/enabled | not null default true | index | admin write | config | MVP_1 |
| `created_at`, `updated_at` | Timestamps | not null | default now | system | DB | MVP_1 |

#### `scenarios` - NEW canonical runtime registry

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Scenario id 1-64 | PK integer | check between 1 and 64 | authenticated read; admin write | runtime registry | MVP_1 |
| `service_id` | Service mapping | FK `hr_services(id)`, not null | index | read | registry | MVP_1 |
| `name` | Scenario name | not null | unique with service optional | read | registry | MVP_1 |
| `assistant_role` | Boundary role | not null | enum `ANSWER`, `GUIDE`, `PREPARE_AND_HANDOFF`, `HUMAN_FIRST`; index | read | registry | MVP_1 |
| `data_dependency` | Data need | not null | enum six values; index | read | registry | MVP_1 |
| `runtime_source_status` | Runtime source reality | not null | enum `IN_PRODUCT`, `SIMULATED_IN_PRODUCT`, `EXTERNAL_REAL`, `EXTERNAL_ASSUMED`, `HUMAN`, `KNOWLEDGE`, `NOT_AVAILABLE`; index | read | runtime contract | MVP_1 |
| `source_of_truth_label` | Human-readable SoT | not null | no URL required | read | registry | MVP_1 |
| `max_runtime_action` | Max action allowed | not null | enum `NONE`, `LINK_ONLY`, `PREFILL_DRAFT`, `CREATE_CASE`; no MVP `READ_STATUS`/`CREATE_REQUEST` | read | runtime registry | MVP_1 |
| `final_owner_department_id` | Accountable owner | FK `hr_departments(id)`, nullable for `Line Manager`/`Business leader` owners | index | read | normalized RACI | MVP_1 |
| `final_owner_role` | Accountable non-department owner | nullable | check one of department or role present | read | normalized RACI | MVP_1 |
| `sensitivity` | Scenario sensitivity | not null | enum Low/Medium/High/Critical; index | read | registry | MVP_1 |
| `mvp_phase` | Scope phase | not null | enum `MVP_1`, `MVP_2`, `FUTURE`, `OUT_OF_MVP`; index | read | runtime registry | MVP_1 |
| `runtime_behavior` | Router guidance | not null | text | read | runtime registry | MVP_1 |
| `user_facing_action_label` | UI wording | nullable | no "demo/simulated/synthetic" check by content review | read | runtime contract | MVP_1 |
| `active` | Enabled | not null default true | index | admin write | config | MVP_1 |

Index đề xuất: `(mvp_phase, max_runtime_action)`, `(assistant_role, data_dependency)`, `(service_id)`, `(sensitivity)`.

#### `scenario_allowed_data_fields` - NEW config

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Row id | PK | primary key | admin write | config | MVP_1 |
| `scenario_id` | Scenario | FK `scenarios(id)`, not null | index | read | runtime registry | MVP_1 |
| `field_key` | Stable field key | not null | unique per scenario | read | data minimization | MVP_1 |
| `label` | User-facing label | not null | no sensitive raw field unless allowed | read | product copy | MVP_1 |
| `required_for_prefill` | Needed for draft | not null default false | index | read | boundary rule | MVP_1 |
| `pii_class` | Field sensitivity | not null | enum Low/Medium/High/Critical | access filter | privacy policy | MVP_1 |
| `storage_policy` | Whether stored | not null | enum `do_not_store`, `store_case_only`, `store_message_ok`, `store_metadata_only` | enforced by service | privacy policy | MVP_1 |

#### `documents` - EXTEND existing as knowledge document

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| existing columns | Existing document registry | existing | keep existing indexes | HR admin write, employee read only user-facing docs | current DB | MVP_1 |
| `doc_type` | Policy/SOP/FAQ/handbook/form/legal_basis/directory | not null default `policy` after backfill | enum; index | read filter | KB spec | MVP_1 |
| `visibility` | Runtime retrieval pool | not null | enum `user_facing`, `offline_compliance`, `admin_only`, `non_rag`; index | RLS filter | KB architecture | MVP_1 |
| `hr_service_id` | Primary service | FK `hr_services(id)`, nullable | index | read | KB mapping | MVP_1 |
| `owner_department_id` | Document owner | FK `hr_departments(id)`, nullable | index | HR owner/admin write | operating model | MVP_1 |
| `canonical_fact_owner` | Whether source owns facts | not null default false | index | admin write | fact ownership | MVP_1 |
| `applicability_summary` | Human-readable scope | nullable | none | read | policy owner | MVP_1 |
| `review_cycle` | Review cadence | nullable | enum monthly/quarterly/annual/ad_hoc optional | admin | governance | FUTURE |

Current `authority`, `provenance`, `tenant` from migration 0004 remain useful. `source_type` becomes legacy display/backward-compatible field.

#### `document_versions` - NEW optional but recommended MVP-1

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Version id | PK | primary key | admin write | document admin | MVP_1 |
| `document_id` | Parent document | FK `documents(id)`, not null | index | read | documents | MVP_1 |
| `version_label` | Version | not null | unique per document | read | document admin | MVP_1 |
| `effective_date` | Effective date | nullable | index | read | document admin | MVP_1 |
| `status` | Version status | not null | enum draft/active/superseded/archived; partial unique active per document | read filter | document admin | MVP_1 |
| `source_file` | File pointer | not null | index | admin | storage | MVP_1 |
| `checksum` | File integrity | nullable | unique optional | admin | ingestion | MVP_1 |
| `created_at` | Timestamp | not null | default now | system | DB | MVP_1 |

Nếu muốn giảm migration, có thể defer `document_versions` và dùng columns hiện có trong `documents`, nhưng version table giúp future-proof citation/effective_date.

#### `knowledge_chunks` - NEW metadata mirror

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Chunk id | PK text/uuid matching Chroma id | primary key | read via citation access | ingestion | MVP_1 |
| `document_version_id` | Source version | FK not null | index | read | ingestion | MVP_1 |
| `chroma_collection` | Vector collection | not null | index | admin | Chroma | MVP_1 |
| `section_path` | Source section | nullable | index optional | read | ingestion | MVP_1 |
| `page_start`, `page_end` | Citation locator | nullable | check page order | read | ingestion | MVP_1 |
| `chunk_order` | Ordering | not null | index | read | ingestion | MVP_1 |
| `visibility` | Retrieval visibility | not null | enum same as documents | RLS filter | document | MVP_1 |
| `metadata` | Extra metadata | nullable jsonb | GIN optional | admin/read citation | ingestion | MVP_1 |

#### `document_applicability` - NEW config

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Row id | PK | primary key | admin write | policy owner | MVP_1 |
| `document_id` | Document | FK not null | index | read | documents | MVP_1 |
| `dimension` | Applicability dimension | not null | enum `contract_type`, `employment_status`, `department`, `location`, `tenure_band`, `role` | read | policy | MVP_1 |
| `value` | Dimension value | not null | index | read | policy | MVP_1 |
| `include` | Include/exclude | not null default true | none | read | policy | MVP_1 |

#### `legal_basis` - NEW compliance mapping

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Row id | PK | primary key | HR/admin only by default | compliance | MVP_1 |
| `document_id` | Internal document | FK `documents(id)`, not null | index | HR/admin | KB authoring | MVP_1 |
| `legal_source_label` | Law/source label | not null | index | HR/admin | official law archive | MVP_1 |
| `topic` | Compliance topic | not null | index | HR/admin | authoring | MVP_1 |
| `usage` | Why referenced | not null | enum `minimum_right`, `limit`, `obligation`, `traceability`, `benchmark` | HR/admin | authoring | MVP_1 |
| `user_facing_default` | Retrieval default | not null default false | check false for law archive | HR/admin | policy | MVP_1 |
| `notes` | Internal note | nullable | none | HR/admin | compliance | MVP_1 |

#### Existing chat tables - EXTEND

| table | columns to add | purpose | constraints/indexes | RLS/access | phase |
|---|---|---|---|---|---|
| `conversations` | keep existing | Chat session only, not HR business object | user_id index | own conversation; HR admin only if policy allows | MVP_1 |
| `messages` | `scenario_id`, `assistant_role`, `max_runtime_action`, `boundary_decision_json`, `pii_risk` | Store boundary result and support evaluation | FK scenario nullable, index scenario/action, pii enum | own messages; HR/admin only with privacy rules | MVP_1 |
| `chat_requests` | `scenario_id`, `runtime_source_status`, `max_runtime_action`, `action_result_type`, `refusal_reason`, `handoff_target_department_id` | Async request state aligned to runtime registry | FK indexes, action enum | requester only; admin/audit scoped | MVP_1 |

#### `access_scopes` - NEW security config

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Scope id | PK | primary key | admin write | security config | MVP_1 |
| `scope_code` | Stable scope | not null | unique | read/admin | security config | MVP_1 |
| `role` | App role | nullable | index | admin | RBAC | MVP_1 |
| `department_id` | Department scope | FK nullable | index | admin | operating model | MVP_1 |
| `max_sensitivity` | Max sensitivity readable | not null | enum | enforced by policies | security | MVP_1 |
| `can_create_case` | Case permission | not null default false | index | admin | security | MVP_2 |

#### `audit_events` - NEW

| column | purpose | PK/FK/nullability | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `id` | Audit id | PK | primary key | admin/security read | system | MVP_1 |
| `actor_id` | User performing action | FK `profiles(id)`, nullable for system | index | security | system | MVP_1 |
| `event_type` | Action type | not null | index | security | app | MVP_1 |
| `entity_type`, `entity_id` | Target | not null | composite index | security | app | MVP_1 |
| `scenario_id` | Scenario context | FK nullable | index | security | runtime registry | MVP_1 |
| `sensitivity` | Audit sensitivity | not null | enum/index | security | app | MVP_1 |
| `metadata` | Redacted metadata | nullable jsonb | no raw PII | security | app | MVP_1 |
| `created_at` | Timestamp | not null | index default now | security | DB | MVP_1 |

#### MVP-2 Case Tables

| table | key columns | purpose | constraints/indexes | RLS/access | source | phase |
|---|---|---|---|---|---|---|
| `case_types` | `id` PK, `code` unique, `name`, `service_id` FK, `allowed_sensitivity`, `default_owner_department_id` FK, `enabled` | Allowlist administrative case types | unique code, service index | admin write, authenticated read labels | service catalog | MVP_2 |
| `hr_cases` | `id` PK, `case_code` unique, `case_type_id` FK, `scenario_id` FK, `requester_id` FK, `owner_department_id` FK, `assignee_id` FK nullable, `status`, `priority`, `sensitivity`, `subject`, `intake_summary`, `created_from_chat_request_id` FK, `due_at`, timestamps | Business case replacing generic tickets | status enum, indexes requester/owner/status/due | requester read own non-sensitive; owner dept; admin; no ER confidential in MVP-2 | case management | MVP_2 |
| `handoffs` | `id` PK, `scenario_id` FK, `chat_request_id` FK, `target_department_id` FK, `handoff_reason`, `handoff_payload`, `created_case_id` FK nullable | Store assistant handoff outcome | indexes scenario/target/case | same as case/request | boundary router | MVP_2 |
| `case_assignments` | `id` PK, `case_id` FK, `assignee_id` FK, `assigned_by`, `assigned_at`, `unassigned_at` | Assignment history | index case/assignee | owner dept/admin | case ops | MVP_2 |
| `case_events` | `id` PK, `case_id` FK, `event_type`, `actor_id`, `from_status`, `to_status`, `metadata`, `created_at` | Case timeline/audit | index case/time/status | case scoped | case ops | MVP_2 |
| `case_notes` | `id` PK, `case_id` FK, `author_id`, `note_type`, `body_redacted`, `visibility_scope`, `created_at` | Controlled notes | no raw high-risk docs; index case | case scoped; stricter for high | case ops | MVP_2 |
| `sla_tracking` | `id` PK, `case_id` FK, `sla_policy_source`, `started_at`, `due_at`, `breached_at`, `escalated_to_department_id` FK | SLA tracking | index due/breached | case scoped | SLA config | MVP_2 |

MVP-2 allowlist: scenarios 13, 17, 20, 27, 28, 45. Scenario 54 and other ER/confidential scenarios remain future until proper ACL/privacy model exists.

### Current To Target Migration Map

| current | target | decision | approach |
|---|---|---|---|
| `auth.users` | identity source | KEEP | Production auth source-of-truth. |
| `public.users` SQLAlchemy model | local test adapter only or remove | REPLACE/DEPRECATE | Reconcile before migration; do not create production auth duplicate. |
| `profiles` | employee/profile | EXTEND | Add `hr_department_id`; keep existing manager/status fields. |
| `conversations` | conversation | KEEP | Add no HR business meaning. |
| `messages` | message + boundary metadata | EXTEND | Add nullable `scenario_id`, role/action metadata, PII risk. |
| `chat_requests` | request processing | EXTEND | Ensure migration exists; add runtime fields. |
| `tickets` | compatibility only | REPLACE | Freeze new writes after `hr_cases`; optional view maps `hr_cases` to old ticket DTO during transition. |
| `documents` | knowledge document | EXTEND | Add doc_type, visibility, service/owner/canonical fields. |
| `ingestion_jobs` | ingestion job | KEEP | Ensure migration exists; link to document/version later. |
| `index_jobs` | index job | KEEP | Ensure migration exists; no HR business semantics. |
| `evaluation_runs` | evaluation run | KEEP | Add scenario coverage metrics later if needed. |

### Migration/Backfill Approach

1. Reconcile migration SQL and SQLAlchemy models: production uses `auth.users`; local `users` model removed or isolated.
2. Add config tables: `hr_departments`, `hr_services`, `scenarios`, `scenario_allowed_data_fields`, `access_scopes`, `audit_events`.
3. Backfill departments and services from operating model.
4. Seed 64 scenarios from runtime-revised registry.
5. Extend `documents` and backfill doc_type/visibility/service/owner.
6. Add `document_versions`, `knowledge_chunks`, `document_applicability`, `legal_basis`.
7. Extend `messages` and `chat_requests` with nullable boundary fields.
8. For MVP-2, add `case_types`, `hr_cases`, `handoffs`, `case_assignments`, `case_events`, `case_notes`, `sla_tracking`.
9. Stop new writes to `tickets`; migrate existing rows to `hr_cases` only if needed, else keep as legacy.
10. Add RLS policies after table creation and before enabling `CREATE_CASE`.

## Workstream B - Knowledge/Data Specification

### Final Document Inventory

| service | policy | SOP | FAQ | manager guide | forms/channel spec | owner | SLA | escalation | applicability | legal_basis |
|---|---|---|---|---|---|---|---|---|---|---|
| Leave | Quy chế Nghỉ phép V-Nova | SOP gửi/đổi/hủy yêu cầu nghỉ | FAQ nghỉ phép | Có | Leave draft/instruction | C&B | Theo service catalog | HRBP/C&B | contract, tenure, employment_status | Có |
| Attendance | Quy định Chấm công | SOP bổ sung/điều chỉnh công | FAQ chấm công | Có | Attendance correction draft | HR Ops | Theo baseline | HRBP nếu dispute | shift/location | Có |
| OT | Chính sách OT | SOP đăng ký OT | FAQ OT | Có | OT draft/instruction | C&B/HR Ops | Theo baseline | C&B/HRBP | employee group, work schedule | Có |
| WFH | Chính sách WFH | SOP đăng ký WFH | FAQ WFH | Có | WFH draft/instruction | HR Ops | Theo baseline | HRBP | role/location/team | Có nếu có |
| Payroll | Quy chế Lương, Thưởng, Phụ cấp | SOP payroll inquiry | FAQ payslip/payroll | Không | Payroll inquiry draft | C&B | Theo payroll SLA | C&B lead/Finance | employee group, pay cycle | Có |
| Benefits/Insurance | Chính sách Bảo hiểm & Phúc lợi | SOP claim bảo hiểm | FAQ benefits | Không | Insurance checklist/channel | C&B | Theo insurer/C&B | C&B lead | employee group/dependent | Có |
| Onboarding | Chính sách Onboarding | SOP hoàn tất hồ sơ onboarding | FAQ nhân viên mới | Có | Onboarding docs checklist | HR Ops | Theo onboarding SLA | HR Ops lead | new hire status | Có nếu cần |
| Offboarding | Chính sách Offboarding | SOP bàn giao/nghỉ việc | FAQ offboarding | Có | Offboarding checklist | HR Ops/HRBP | Theo baseline | HRBP/C&B/IT/Admin | contract/status | Có |
| Performance/KPI | Quy chế KPI/Performance Review | SOP review và dispute guidance | FAQ performance | Có | KPI conversation draft | HRBP | Theo review cycle | ER nếu conflict | role/level | Không hoặc compliance nội bộ |
| Career/Promotion | Chính sách Career/Promotion | SOP career conversation | FAQ promotion/salary review | Có | Career conversation draft | HRBP/C&B | Theo cycle | Business leader | level/job family | Không hoặc compliance nội bộ |
| L&D | Chính sách Đào tạo | SOP đăng ký/tài trợ đào tạo | FAQ training | Có | Training registration/budget draft | L&D | Theo baseline | Finance nếu ngân sách | role/level | Có nếu cam kết đào tạo |
| TA/Internal Mobility | Chính sách Internal Mobility | SOP ứng tuyển nội bộ | FAQ internal job | Có | Internal job guidance | TA | Theo TA SLA | HRBP | employment_status/performance | Không hoặc compliance nội bộ |
| ER/Grievance | Chính sách Khiếu nại/ER | SOP liên hệ ER an toàn | FAQ grievance policy | Có | ER safe channel guidance | ER | Theo severity | Legal | all employees | Có |
| Finance/Expense | Chính sách Công tác phí/Expense | SOP advance/reimbursement | FAQ expense | Có nếu manager approve | Expense guidance | Finance | Theo Finance SLA | Finance lead | role/trip type | Có nếu tax/accounting |
| IT/Admin | Chính sách thiết bị/quyền truy cập | SOP yêu cầu thiết bị/badge | FAQ workplace admin | Có | IT/Admin contact guidance | IT/Admin | Theo IT/Admin SLA | Admin/Security | role/location | Không |
| Privacy/Legal/Immigration | Chính sách Privacy/Legal Support | SOP privacy/work permit inquiry | FAQ privacy/work permit | Không | Legal/HR Ops guidance | Legal | Theo severity | Legal lead | citizenship/location | Có |

### Knowledge Coverage Matrix For 64 Scenarios

| scenario_id | required knowledge | planned document | coverage |
|---:|---|---|---|
| 1 | Số ngày phép, điều kiện thâm niên, loại hợp đồng | Quy chế Nghỉ phép; FAQ nghỉ phép | Planned |
| 2 | Cách chuẩn bị yêu cầu nghỉ, trường thông tin, manager approval | SOP gửi yêu cầu nghỉ; Forms Registry | Planned |
| 3 | Nghỉ khẩn cấp, thời điểm báo, manager channel | SOP gửi yêu cầu nghỉ; FAQ nghỉ phép | Planned |
| 4 | Điều kiện leave exception, âm phép, unpaid/exception path | Quy chế Nghỉ phép; Manager Guide Leave | Planned |
| 5 | Nghỉ ốm, chứng từ, privacy medical | Quy chế Nghỉ phép; SOP nghỉ ốm | Planned |
| 6 | Nghỉ thai sản/cha mẹ, hồ sơ, C&B owner | Chính sách Benefits/Leave; SOP parental leave | Planned |
| 7 | Nghỉ không lương, manager/HRBP process | Quy chế Nghỉ phép; Manager Guide Leave | Planned |
| 8 | Lịch nghỉ lễ, ngày áp dụng | Employee Handbook; Holiday Notice | Planned |
| 9 | SLA manager approval, escalation khi quá hạn | SOP gửi yêu cầu nghỉ; FAQ nghỉ phép | Planned |
| 10 | Hủy/đổi đơn nghỉ | SOP gửi yêu cầu nghỉ; Forms Registry | Planned |
| 11 | Bổ sung công, required fields, deadline | Quy định Chấm công; SOP bổ sung công | Planned |
| 12 | Đi trễ, báo manager, ghi nhận công | Quy định Chấm công; FAQ chấm công | Planned |
| 13 | Lỗi check-in WFH, HR Ops/IT path | SOP bổ sung công; IT/Admin guidance | Planned |
| 14 | Đăng ký OT trước khi làm, manager approval | Chính sách OT; SOP đăng ký OT | Planned |
| 15 | Cách tính OT mức nguyên tắc | Chính sách OT; FAQ OT | Planned |
| 16 | Đổi ca/lịch làm việc, manager decision | Quy định Chấm công; Manager Guide Attendance | Planned |
| 17 | Attendance dispute sau từ chối | SOP bổ sung công; Manager Guide Attendance | Planned |
| 18 | Vắng mặt không báo trước, human-first boundary | Quy định Chấm công; ER safe handling guide | Planned |
| 19 | Cách xem payslip không có portal thật | FAQ payroll; Forms Registry | Planned |
| 20 | Payroll discrepancy, draft inquiry, no personal state | SOP payroll inquiry; FAQ payroll | Planned |
| 21 | Đổi tài khoản ngân hàng qua kênh bảo mật | SOP employee data change; Payroll FAQ | Planned |
| 22 | Chứng từ thuế TNCN | SOP tax document request; FAQ payroll | Planned |
| 23 | Timeline thưởng chung, không cam kết cá nhân | Quy chế Lương Thưởng; FAQ thưởng | Planned |
| 24 | Điều kiện phụ cấp chung | Quy chế Lương Thưởng Phụ cấp; FAQ benefits/payroll | Planned |
| 25 | Insurance claim checklist, không thu y tế | Chính sách Bảo hiểm; SOP insurance claim | Planned |
| 26 | Người phụ thuộc/bảo hiểm, secure channel | Chính sách Benefits; SOP dependent registration | Planned |
| 27 | Payroll deduction inquiry | SOP payroll inquiry; FAQ payroll | Planned |
| 28 | Missing onboarding docs checklist | SOP onboarding; FAQ nhân viên mới | Planned |
| 29 | Probation to official, manager/HRBP owner | Chính sách Probation; Manager Guide Probation | Planned |
| 30 | Probation extension concern | Chính sách Probation; ER safe handling guide | Planned |
| 31 | Gia hạn hợp đồng | Chính sách Contract Lifecycle; FAQ contract | Planned |
| 32 | Contract changes | Chính sách Contract Lifecycle; HRBP Guide | Planned |
| 33 | Employee transfer | Chính sách Internal Mobility; Manager Guide Mobility | Planned |
| 34 | Profile data change | SOP employee data change; Forms Registry | Planned |
| 35 | Emergency contact change | SOP employee data change; Forms Registry | Planned |
| 36 | Resignation process, human-first | Chính sách Offboarding; SOP resignation guidance | Planned |
| 37 | Exit handover checklist | SOP offboarding; Manager Guide Offboarding | Planned |
| 38 | Final settlement guidance, no amount calculation | Quy chế Lương/Offboarding; FAQ final settlement | Planned |
| 39 | KPI goal clarification with manager | Quy chế KPI; Manager Guide Performance | Planned |
| 40 | KPI dispute boundary | SOP KPI dispute guidance; ER safe handling | Planned |
| 41 | Performance review timeline | Quy chế KPI; FAQ performance | Planned |
| 42 | Promotion/salary review human-owned | Chính sách Career/Promotion; Manager Guide Career | Planned |
| 43 | Development plan conversation | Chính sách L&D; Manager Guide Development | Planned |
| 44 | Training registration | SOP training registration; FAQ L&D | Planned |
| 45 | Training budget/certification request | Chính sách L&D; SOP training budget | Planned |
| 46 | Internal job application | Chính sách Internal Mobility; FAQ TA | Planned |
| 47 | WFH normal request | Chính sách WFH; SOP WFH request | Planned |
| 48 | WFH exception | Chính sách WFH; Manager Guide WFH | Planned |
| 49 | Equipment request guidance | IT/Admin workplace guide; Forms Registry | Planned |
| 50 | Access badge guidance | IT/Admin workplace guide; Forms Registry | Planned |
| 51 | Manager conflict safe channel | ER policy; ER safe handling guide | Planned |
| 52 | Harassment/discrimination concern | ER policy; Safe channel guidance | Planned |
| 53 | Grievance policy | ER grievance policy; FAQ grievance | Planned |
| 54 | Formal grievance submission boundary | ER policy; Safe channel guidance | Planned |
| 55 | Disciplinary action notice boundary | Disciplinary process policy; ER guide | Planned |
| 56 | Conflict of interest/ethics | Code of Conduct; Ethics channel guide | Planned |
| 57 | Stress/burnout support | Employee support guide; HRBP/EAP guidance | Planned |
| 58 | Workplace safety incident | Safety incident guide; Admin/Safety channel | Planned |
| 59 | Business trip advance | Business Trip/Expense Policy; Finance SOP | Planned |
| 60 | Expense reimbursement | Expense Policy; Reimbursement SOP | Planned |
| 61 | Employment confirmation/reference letter | HR Ops document request SOP | Planned |
| 62 | Data privacy/access correction request | Privacy Policy; Data request SOP | Planned |
| 63 | Reporting line change | Org Change/HRBP guide | Planned |
| 64 | Immigration/work permit support | Legal/HR Ops work permit guide | Planned |

### Fact Ownership Matrix

| fact area | canonical owner document | may reference but not own |
|---|---|---|
| Annual leave entitlement | Quy chế Nghỉ phép | FAQ, Handbook, SOP |
| Leave request deadline/form/manager approval | SOP gửi yêu cầu nghỉ | FAQ, Forms Registry |
| Emergency leave notification | SOP gửi yêu cầu nghỉ | FAQ |
| Attendance correction deadline/fields | SOP bổ sung công | FAQ |
| Attendance policy rules | Quy định Chấm công | SOP, FAQ |
| OT eligibility and pay rule | Chính sách OT | FAQ payroll, Handbook |
| OT registration process | SOP đăng ký OT | FAQ |
| WFH eligibility | Chính sách WFH | FAQ, Manager Guide |
| Payroll calendar/cutoff | Quy chế Lương Thưởng Phụ cấp | Payroll FAQ |
| Payroll discrepancy process | SOP payroll inquiry | FAQ |
| Bank/profile data update channel | SOP employee data change | FAQ |
| Benefits eligibility | Chính sách Bảo hiểm & Phúc lợi | FAQ |
| Insurance claim checklist | SOP insurance claim | FAQ |
| Probation process | Chính sách Probation | Manager Guide, FAQ |
| KPI timeline/rating process | Quy chế KPI | FAQ, Manager Guide |
| KPI dispute process | SOP KPI dispute guidance | FAQ |
| Promotion/salary review process | Chính sách Career/Promotion | Manager Guide, FAQ |
| Resignation notice/offboarding process | Chính sách Offboarding | SOP resignation, FAQ |
| Final settlement process | Quy chế Offboarding + C&B settlement SOP | FAQ |
| Grievance rights/channel | ER grievance policy | FAQ, Safe channel guide |
| Disciplinary process | Disciplinary process policy | ER guide |
| Expense/advance rule | Business Trip/Expense Policy | Finance SOP, FAQ |
| HR owner/SLA/escalation | HR Service Catalog | Handbook, FAQ |
| Runtime action boundary | Assistant Boundary Playbook | Router/evaluation |

### Cross-Document Consistency Rules

- Department names must use: HR Ops, C&B, HRBP, TA, L&D, ER, Finance, Legal, IT, Admin, Safety.
- User-facing copy must not show "simulated", "synthetic", or "demo".
- Use "Chuẩn bị yêu cầu", "Bản nháp", "Hướng dẫn gửi", "Người phụ trách" for non-integrated surfaces.
- Working hours, payroll cutoff, leave deadline, OT deadline and SLA values must be defined once in the relevant policy/SOP and referenced elsewhere.
- Handbook and FAQ do not own canonical facts; they summarize and point to policy/SOP.
- Legal/public sources are authoring/compliance only, never indexed into employee RAG by default.
- If a question asks personal state and source is not integrated, answer must state no access and route to owner/channel.
- Approval role terms must be consistent: Line Manager, HRBP, C&B, HR Ops, Business leader, ER, Legal.
- Escalation path must always include owner, condition for escalation, and sensitivity note.

### Research/Crawl Source Plan

| domain | official law sources to read | public HR pattern research | pattern-only usage | V-Nova business rules to design |
|---|---|---|---|---|
| Leave | Bộ luật Lao động, nghị định/thông tư liên quan thời giờ nghỉ ngơi | Public leave policies/employee handbooks | Workflow wording, exception patterns | entitlement, carry-over, expiry, half-day, emergency leave |
| Attendance/Working hours | Bộ luật Lao động, working time/overtime rules | Attendance policies, timesheet correction SOP | Correction deadline, evidence pattern | cutoff, manager confirmation, dispute path |
| OT | Labor overtime rules, wage/overtime provisions | OT approval policies | Pre-approval workflow | eligible roles, approval threshold, payroll cutoff |
| WFH | Labor safety/general employment obligations where relevant | Remote/hybrid work policies | Eligibility, productivity norms | WFH days, exception process, equipment/security |
| Payroll/Tax | Labor wage provisions, tax guidance, social insurance references | Payroll FAQ, payslip guides | Inquiry triage | pay date, cutoff, adjustment cycle |
| Benefits/Insurance | BHXH/BHYT and insurance-related official rules | Benefits handbooks, insurance claim guides | Claim checklist | company-paid benefits, dependent rules |
| Probation/Contract | Labor contract/probation provisions | Probation review templates | Review checkpoints | review owner, notice timeline, extension handling |
| Performance/KPI | Internal governance; labor rules if compensation/discipline impact | Performance review guides | Calibration/dispute patterns | KPI cycle, rating scale, dispute channel |
| Promotion/Career | Internal governance | Career framework examples | Conversation/checklist patterns | level criteria, salary review cycle |
| Resignation/Offboarding | Labor termination/notice provisions | Offboarding checklists | Handover/task patterns | notice handling, asset return, settlement timeline |
| Grievance/Discipline/ER | Labor discipline, workplace safety, anti-harassment where applicable | Grievance procedures, investigation guides | Safe channel, confidentiality pattern | ER intake, no-chat-testimony rule, escalation |
| L&D | Labor/training cost commitment provisions if applicable | Training reimbursement policies | Budget approval patterns | training budget, bond/reimbursement |
| Expense/Business trip | Tax/accounting guidance as applicable | Expense policies | Receipt/approval patterns | per diem, advance, reimbursement SLA |
| Privacy/Work permit | Data privacy and immigration/work permit official sources | Privacy request SOP, relocation guides | Intake and routing | data request channel, Legal owner |

Public HR policy/handbook/SOP sources are research inputs only. They must not be indexed into employee-facing RAG.

## Review Gate Before Migration/Content

- Physical schema proposal approved.
- Current to target migration map approved.
- Auth strategy approved: Supabase Auth with `auth.users`.
- Runtime registry seeded design approved.
- MVP-1 knowledge coverage has no missing scenario.
- Fact ownership matrix approved.
- Cross-document consistency rules approved.
- Research/crawl plan approved.
