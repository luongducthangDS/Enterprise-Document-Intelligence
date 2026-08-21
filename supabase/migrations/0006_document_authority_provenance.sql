-- ============================================================
-- Taxonomy 2 chiều cho documents: authority x provenance
-- ============================================================

alter table public.documents
  add column if not exists authority text
    check (authority in ('tenant_official_policy','government_law','public_reference','public_template','non_rag')),
  add column if not exists provenance text
    check (provenance in ('customer_provided','government_source','public_web','synthetic_demo','internal_config')),
  add column if not exists tenant text not null default '';

comment on column public.documents.authority is
  'Vai trò của tài liệu trong business world — quyết định thứ tự ưu tiên khi các nguồn nói khác nhau.';
comment on column public.documents.provenance is
  'Nguồn gốc thật của dữ liệu. provenance=synthetic_demo bị loại khỏi truy vấn khi DATA_MODE=production.';
comment on column public.documents.tenant is
  'Slug doanh nghiệp sở hữu tài liệu. Chuỗi rỗng nghĩa là không thuộc doanh nghiệp nào.';

update public.documents set
  authority = case source_type
    when 'government_law'  then 'government_law'
    when 'official_policy' then 'public_reference'
    when 'public_article'  then 'public_reference'
    when 'public_template' then 'public_template'
    when 'synthetic'       then 'tenant_official_policy'
    when 'FILE_UPLOAD'     then case when is_official_policy then 'tenant_official_policy' else 'public_reference' end
    else 'non_rag'
  end,
  provenance = case source_type
    when 'government_law'  then 'government_source'
    when 'synthetic'       then 'synthetic_demo'
    when 'official_policy' then 'public_web'
    when 'public_article'  then 'public_web'
    when 'public_template' then 'public_web'
    when 'FILE_UPLOAD'     then 'customer_provided'
    else 'internal_config'
  end,
  tenant = case when source_type = 'synthetic' then 'nexatech' else tenant end
where authority is null;

update public.documents
  set is_official_policy = (authority = 'tenant_official_policy');

alter table public.documents
  alter column authority set not null,
  alter column provenance set not null;

create index if not exists documents_provenance_idx on public.documents (provenance);
create index if not exists documents_tenant_authority_idx on public.documents (tenant, authority);

