-- Runtime document ACL: persist the same authorization attributes enforced in Chroma.
alter table public.documents
  add column if not exists department text not null default 'HR',
  add column if not exists access_scope text not null default 'RESTRICTED',
  add column if not exists authorized_role text,
  add column if not exists owner_user_id uuid references public.profiles(id) on delete set null,
  add column if not exists authorization_source text not null default 'RUNTIME_UPLOAD';

update public.documents
set owner_user_id = uploaded_by
where owner_user_id is null and uploaded_by is not null;

alter table public.documents drop constraint if exists documents_source_file_key;
create unique index if not exists documents_tenant_source_file_uidx
  on public.documents (tenant, source_file);
create index if not exists documents_runtime_acl_idx
  on public.documents (tenant, authorization_source, access_scope, department, authorized_role, owner_user_id);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'documents_access_scope_check') then
    alter table public.documents add constraint documents_access_scope_check
      check (access_scope in ('COMPANY_WIDE','DEPARTMENT','ROLE','RESTRICTED'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'documents_role_scope_check') then
    alter table public.documents add constraint documents_role_scope_check
      check (access_scope <> 'ROLE' or authorized_role is not null);
  end if;
end $$;