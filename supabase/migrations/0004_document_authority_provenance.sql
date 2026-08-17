-- ============================================================
-- Taxonomy 2 chiều cho documents: authority x provenance
--
-- `source_type` gộp hai câu hỏi khác nhau vào một trục nên không diễn đạt được
-- trường hợp trung tâm của sản phẩm: một tài liệu VỪA là chính sách nội bộ
-- chính thức của tenant demo, VỪA có nguồn gốc synthetic. Ép về một trục buộc
-- phải chọn giữa nói dối về nguồn gốc và vô hiệu hoá use case doanh nghiệp.
--
-- source_type được GIỮ NGUYÊN (không đổi giá trị của bất kỳ hàng nào) để
-- Citation schema, agent DTO và frontend hiện có không vỡ. Nó trở thành cột
-- legacy/hiển thị; authority + provenance mới là thứ quyết định thẩm quyền
-- nguồn và lọc theo môi trường dữ liệu.
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
  'Slug doanh nghiệp sở hữu tài liệu. '''' = không thuộc doanh nghiệp nào (luật, template, tham khảo).';

-- Backfill khớp đúng data/metadata/document_registry.csv.
-- Lưu ý phân loại lại có chủ đích ở 2 nhóm:
--   synthetic       -> tenant_official_policy : bộ policy của tenant demo V-Nova
--   official_policy -> public_reference       : quy định nội bộ VinFast + quy trình
--                      tuyển dụng Vingroup là policy THẬT nhưng của doanh nghiệp
--                      KHÁC, không phải tenant đang được phục vụ.
update public.documents set
  authority = case source_type
    when 'government_law'  then 'government_law'
    when 'official_policy' then 'public_reference'
    when 'public_article'  then 'public_reference'
    when 'public_template' then 'public_template'
    when 'synthetic'       then 'tenant_official_policy'
    else 'non_rag'
  end,
  provenance = case source_type
    when 'government_law'  then 'government_source'
    when 'synthetic'       then 'synthetic_demo'
    when 'official_policy' then 'public_web'
    when 'public_article'  then 'public_web'
    when 'public_template' then 'public_web'
    else 'internal_config'
  end,
  tenant = case when source_type = 'synthetic' then 'v-nova' else '' end
where authority is null;

-- is_official_policy giờ chỉ còn MỘT nghĩa: chính sách của tenant đang phục vụ.
-- Văn bản pháp luật là nguồn có thẩm quyền nhưng không phải chính sách doanh
-- nghiệp, nên cờ này về false — frontend phân biệt bằng authority, không bằng cờ.
update public.documents
  set is_official_policy = (authority = 'tenant_official_policy');

alter table public.documents
  alter column authority set not null,
  alter column provenance set not null;

-- Lọc theo môi trường dữ liệu chạy trên mọi truy vấn danh sách tài liệu.
create index if not exists documents_provenance_idx on public.documents (provenance);
create index if not exists documents_tenant_authority_idx on public.documents (tenant, authority);
