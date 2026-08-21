import csv
import os
from typing import Literal

from pydantic import BaseModel

REGISTRY_PATH = "data/metadata/document_registry.csv"

SourceType = Literal[
    "government_law",
    "official_policy",
    "public_template",
    "synthetic",
    "public_article",
    "eval_asset",
    "config",
    "rejected",
]

# source_type mà build_chunks phải bỏ qua — không phải nội dung RAG.
# "official_policy" (chính sách công khai của doanh nghiệp khác), "public_template",
# "public_article" bị loại có chủ đích vì không gắn với kho tri thức nội bộ của tenant.
#
# THAY ĐỔI (2026-08-21): "government_law" được ĐƯA VÀO knowledge database.
# Lý do: Kho tài liệu nội bộ VinBigData bao gồm cả các văn bản pháp luật (bộ luật,
# nghị định, thông tư) làm nguồn tham chiếu bổ sung. Agent được phép trích dẫn
# trực tiếp các văn bản pháp luật này kèm metadata is_official_policy=True và
# authority="government_law" để người dùng phân biệt được nguồn gốc.
# Rào chắn provenance filter tại retrieval node vẫn giữ nguyên — chỉ mở rộng
# allowlist authority cho government_law chunks.
NON_RAG_SOURCE_TYPES = {
    "eval_asset", "config", "rejected",
    "official_policy", "public_template", "public_article",
}

# ---------------------------------------------------------------------------
# Taxonomy 2 chiều: authority (vai trò trong business world) x provenance
# (nguồn gốc thật của dữ liệu).
#
# `source_type` cũ gộp hai câu hỏi khác nhau vào một trục, nên không diễn đạt
# được trường hợp quan trọng nhất của sản phẩm: một tài liệu VỪA là chính sách
# nội bộ chính thức của tenant demo, VỪA có nguồn gốc synthetic. Ép nó về một
# trục buộc ta phải chọn giữa "nói dối về nguồn gốc" (gắn official_policy) và
# "vô hiệu hoá use case doanh nghiệp" (gắn synthetic rồi từ chối trả lời).
#
# source_type được GIỮ NGUYÊN cho mọi tài liệu — nó vẫn là contract của Supabase
# CHECK constraint, Citation schema và frontend. Nó trở thành legacy/hiển thị;
# authority + provenance mới là thứ quyết định xếp hạng nguồn và lọc theo môi
# trường. Không đổi source_type = không mất dấu vết provenance thật ở tầng nào.
# ---------------------------------------------------------------------------

Authority = Literal[
    "tenant_official_policy",  # chính sách nội bộ chính thức CỦA TENANT đang phục vụ
    "government_law",  # văn bản quy phạm pháp luật
    "public_reference",  # tài liệu tham khảo công khai, gồm cả policy THẬT của doanh nghiệp KHÁC
    "public_template",  # biểu mẫu/template công khai, không gắn doanh nghiệp nào
    "non_rag",  # eval asset / config — không phải nội dung RAG
]

Provenance = Literal[
    "customer_provided",  # doanh nghiệp khách hàng cung cấp (production)
    "government_source",  # nguồn nhà nước
    "public_web",  # thu thập từ internet công khai
    "synthetic_demo",  # sinh mô phỏng phục vụ xây dựng/demo sản phẩm
    "internal_config",  # tài sản nội bộ của project (eval, config)
]

# Thứ tự thẩm quyền khi nhiều nguồn cùng trả lời một câu hỏi. Số nhỏ = ưu tiên
# cao. Dùng cho xếp hạng/nhãn nguồn, KHÔNG dùng để sắp lại thứ tự vật lý của
# context block (xem ghi chú trong src/agents/nodes/generation.py).
AUTHORITY_RANK: dict[str, int] = {
    "tenant_official_policy": 0,
    "government_law": 1,
    "public_reference": 2,
    "public_template": 3,
    "non_rag": 99,
}

# provenance KHÔNG được dùng để trả lời trong môi trường production — dữ liệu mô
# phỏng chỉ tồn tại để demo cách hệ thống xử lý policy nội bộ khi triển khai thật.
DEMO_ONLY_PROVENANCE = {"synthetic_demo"}

# ---------------------------------------------------------------------------
# Lifecycle của tài liệu nội bộ — filter bắt buộc theo NexaTech Type-C contract
# v3.1.0 (frozen), mục "Production retrieval chỉ được dùng frozen internal
# corpus": publication_status/artifact_state/retrieval_enabled quyết định một
# chunk có được TRUY VẤN hay không, tách biệt với authority/provenance (vai
# trò + nguồn gốc). Ba field này CHƯA tồn tại trước khi có contract — mặc định
# "active"/"frozen"/True cho toàn bộ tài liệu hiện có (không có tài liệu nào bị
# supersede), suy từ CSV khi có, để migrate không phá registry cũ.
PublicationStatus = Literal["active", "superseded", "draft"]
ArtifactState = Literal["frozen", "draft"]

DEFAULT_PUBLICATION_STATUS: PublicationStatus = "active"
DEFAULT_ARTIFACT_STATE: ArtifactState = "frozen"
# Sentinel "không có ngày hết hạn" — KHÔNG dùng None/"". Chroma bỏ hẳn key có
# giá trị None khỏi metadata khi ghi (xem ChunkMetadata.to_chroma_metadata),
# nên filter `{"expiry_date": {"$gte": query_date}}` sẽ loại nhầm MỌI chunk
# không có ngày hết hạn (field vắng mặt không khớp $gte — cùng lỗi fail-open
# đã gặp với $ne trên field thiếu, xem retrieval.py::_provenance_filter). Một
# ngày xa tương lai đảm bảo field LUÔN tồn tại và luôn qua được so sánh $gte.
NO_EXPIRY_SENTINEL = "9999-12-31"


# Suy authority/provenance từ source_type cho registry chưa có 3 cột mới. Bảng
# này CHÍNH LÀ đợt phân loại lại: `synthetic` (8 file V-NOVA) lên
# tenant_official_policy, còn `official_policy` (quy định nội bộ VinFast + quy
# trình tuyển dụng Vingroup — policy THẬT nhưng của doanh nghiệp KHÁC, không
# phải tenant đang phục vụ) xuống public_reference.
_LEGACY_SOURCE_TYPE_MAP: dict[str, tuple[str, str]] = {
    "government_law": ("government_law", "government_source"),
    "official_policy": ("public_reference", "public_web"),
    "public_article": ("public_reference", "public_web"),
    "public_template": ("public_template", "public_web"),
    "synthetic": ("tenant_official_policy", "synthetic_demo"),
    "eval_asset": ("non_rag", "internal_config"),
    "config": ("non_rag", "internal_config"),
    "rejected": ("non_rag", "internal_config"),
}

DEMO_TENANT = "nexatech"

# Ngày mặc định khi effective_date thiếu — 0001-01-01 (luôn <= mọi query_date
# thật) để không chặn nhầm tài liệu chưa khai effective_date. Xem
# date_to_ymd_int()/NO_EXPIRY_SENTINEL cho lý do dùng số nguyên YYYYMMDD thay
# vì chuỗi ISO: Chroma `$lte`/`$gte` CHỈ nhận int/float, không nhận chuỗi (đã
# đo lỗi thật `ValueError: Expected operand value to be an int or a float for
# operator $lte` khi thử filter bằng chuỗi ISO trực tiếp).
DEFAULT_EFFECTIVE_DATE = "0001-01-01"


def date_to_ymd_int(date_str: str) -> int:
    """"YYYY-MM-DD" -> YYYYMMDD (int) — so sánh $lte/$gte được trên Chroma.

    So chuỗi ISO đúng thứ tự thời gian theo từ điển, nhưng Chroma không chấp
    nhận operand chuỗi cho $lte/$gte nên phải ép về số. Parse lỗi (định dạng
    khác) coi như "0001-01-01" (luôn <= mọi ngày thật) thay vì raise — tài
    liệu không hợp lệ ngày tháng vẫn nên retrieval được thay vì biến mất im
    lặng; lỗi định dạng nên bắt ở khâu nhập liệu, không phải ở query runtime.
    """
    digits = date_str.replace("-", "").strip()
    if len(digits) == 8 and digits.isdigit():
        return int(digits)
    return 1  # 0001-01-01


class RegistryRow(BaseModel):
    source_file: str
    document_domain: str = "COMPANY_POLICY"  # COMPANY_POLICY | LEGAL | DEPARTMENT_PROCESS | MANAGEMENT | EXTERNAL_REFERENCE | EVALUATION_DATA | USER_PERSONA | SYSTEM_CONFIGURATION | OTHER
    related_departments: str = "[]"  # Semantic business relevance recommendation only (KHÔNG cấp quyền)
    access_scope: str = "COMPANY_WIDE"  # COMPANY_WIDE | DEPARTMENT | ROLE | RESTRICTED | PENDING_REVIEW | CUSTOM
    authorized_departments: str = "[]"  # Danh sách phòng ban được cấp quyền thực tế
    authorized_roles: str = "[]"  # Danh sách vai trò được cấp quyền thực tế
    authorization_status: str = "ACTIVE"  # ACTIVE | PENDING_REVIEW | SUSPENDED | ARCHIVED
    authorization_source: str = "BUSINESS_POLICY"  # OFFICIAL_COMPANY_ISSUANCE | DEPARTMENT_SOP_POLICY | PENDING_BUSINESS_DECISION | ENTERPRISE_ADMIN_CONFIG | EXTERNAL_REFERENCE_DEFAULT_RESTRICTED | SYSTEM_INTERNAL
    classification_source: str = "DETERMINISTIC_AUDIT"  # DETERMINISTIC_AUDIT | LLM_RECOMMENDATION | SYSTEM_CONFIG
    is_knowledge_doc: bool = True  # False nếu là dữ liệu hệ thống / eval / config
    department: str = "GENERAL"
    sensitivity: str = "INTERNAL"  # PUBLIC | INTERNAL | CONFIDENTIAL | RESTRICTED
    scope: str = "COMPANY_WIDE"  # Legacy compat
    access_category: str = "COMPANY_POLICY"  # Legacy compat
    issuer: str = ""
    document_type: str = ""
    classification_confidence: str = "1.00"
    classification_status: str = "APPROVED"
    classification_reason: str = ""
    category: str
    status: str
    processed_path: str
    chunks_path: str = ""
    indexed_at: str = ""
    source_type: SourceType
    is_official_policy: bool
    caveat: str = ""
    authority: Authority
    provenance: Provenance
    tenant: str = ""
    publication_status: str = DEFAULT_PUBLICATION_STATUS
    artifact_state: str = DEFAULT_ARTIFACT_STATE
    retrieval_enabled: bool = True
    expiry_date: str = NO_EXPIRY_SENTINEL


class ChunkMetadata(BaseModel):
    chunk_id: str
    source_file: str
    source_stem: str
    title: str
    document_domain: str = "COMPANY_POLICY"
    related_departments: str = "[]"  # Semantic relevance only
    access_scope: str = "COMPANY_WIDE"
    authorized_departments: str = "[]"
    authorized_roles: str = "[]"
    authorization_status: str = "ACTIVE"
    authorization_source: str = "BUSINESS_POLICY"
    classification_source: str = "DETERMINISTIC_AUDIT"
    is_knowledge_doc: bool = True
    department: str = "GENERAL"
    sensitivity: str = "INTERNAL"
    access_category: str = "COMPANY_POLICY"  # Legacy compat
    scope: str = "COMPANY_WIDE"  # Legacy compat
    issuer: str = ""
    document_type: str = ""
    category: str
    source_type: str
    is_official_policy: bool
    # authority/provenance/tenant
    authority: str = "public_reference"
    provenance: str = "public_web"
    tenant: str = ""
    publication_status: str = DEFAULT_PUBLICATION_STATUS
    artifact_state: str = DEFAULT_ARTIFACT_STATE
    retrieval_enabled: bool = True
    expiry_date: str = NO_EXPIRY_SENTINEL
    effective_date_ymd: int = 1
    expiry_date_ymd: int = 99991231



    caveat: str = ""
    heading_path: str = ""
    chapter: str | None = None
    article: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    sheet_start: str | None = None
    sheet_end: str | None = None
    chunk_index: int
    char_count: int
    document_code: str | None = None
    version: str | None = None
    effective_date: str | None = None
    owner: str | None = None
    legal_basis: str | None = None
    embedding_model: str | None = None

    def to_chroma_metadata(self) -> dict:
        """Chroma Cloud giới hạn tối đa 32 metadata keys mỗi collection.
        Chỉ xuất 22 trường thực sự cần thiết cho truy vấn (where filter) và hiển thị citation.
        """
        CHROMA_ALLOWED_KEYS = {
            "source_file",
            "title",
            "document_domain",
            "access_scope",
            "department",
            "category",
            "source_type",
            "is_official_policy",
            "authority",
            "provenance",
            "tenant",
            "publication_status",
            "artifact_state",
            "retrieval_enabled",
            "effective_date_ymd",
            "expiry_date_ymd",
            "caveat",
            "heading_path",
            "page_start",
            "page_end",
            "sheet_start",
            "sheet_end",
        }
        return {k: v for k, v in self.model_dump().items() if k in CHROMA_ALLOWED_KEYS and v is not None}




class Chunk(BaseModel):
    text: str
    embedding_text: str
    metadata: ChunkMetadata


def _resolve_taxonomy(row: dict) -> tuple[str, str, str]:
    """Đọc authority/provenance/tenant từ registry, suy từ source_type nếu registry
    chưa có 3 cột mới — để code chạy được cả trước và sau khi migrate CSV."""
    fallback_authority, fallback_provenance = _LEGACY_SOURCE_TYPE_MAP[row["source_type"]]
    authority = (row.get("authority") or "").strip() or fallback_authority
    provenance = (row.get("provenance") or "").strip() or fallback_provenance
    tenant = (row.get("tenant") or "").strip()
    if not tenant and authority == "tenant_official_policy":
        tenant = DEMO_TENANT
    return authority, provenance, tenant


def _resolve_lifecycle(row: dict) -> tuple[str, str, bool, str]:
    """Đọc publication_status/artifact_state/retrieval_enabled/expiry_date từ
    registry, mặc định "active"/"frozen"/True/"" nếu CSV chưa có 4 cột này —
    cùng nguyên tắc migrate-an-toàn với _resolve_taxonomy."""
    publication_status = (row.get("publication_status") or "").strip() or DEFAULT_PUBLICATION_STATUS
    artifact_state = (row.get("artifact_state") or "").strip() or DEFAULT_ARTIFACT_STATE
    retrieval_enabled_raw = (row.get("retrieval_enabled") or "").strip().lower()
    retrieval_enabled = retrieval_enabled_raw != "false"
    expiry_date = (row.get("expiry_date") or "").strip() or NO_EXPIRY_SENTINEL
    return publication_status, artifact_state, retrieval_enabled, expiry_date


def load_registry(path: str = REGISTRY_PATH) -> list[RegistryRow]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            authority, provenance, tenant = _resolve_taxonomy(row)
            publication_status, artifact_state, retrieval_enabled, expiry_date = _resolve_lifecycle(row)
            access_category = (row.get("access_category") or "").strip() or "COMPANY_POLICY"
            doc_domain = (row.get("document_domain") or "").strip() or "INTERNAL_POLICY"
            related_depts = (row.get("related_departments") or "").strip() or "[]"
            scope = (row.get("scope") or "").strip() or "COMPANY_WIDE"
            issuer = (row.get("issuer") or "").strip()
            doc_type = (row.get("document_type") or "").strip()
            conf = (row.get("classification_confidence") or "").strip() or "1.00"
            status = (row.get("classification_status") or "").strip() or "APPROVED"
            access_scope = (row.get("access_scope") or "").strip() or "COMPANY_WIDE"
            auth_depts = (row.get("authorized_departments") or "").strip() or "[]"
            auth_roles = (row.get("authorized_roles") or "").strip() or "[]"
            auth_source = (row.get("authorization_source") or "").strip() or "BUSINESS_POLICY"
            class_source = (row.get("classification_source") or "").strip() or "DETERMINISTIC_AUDIT"
            auth_status = (row.get("authorization_status") or "").strip() or "ACTIVE"
            is_knowledge_raw = (row.get("is_knowledge_doc") or "").strip().lower()
            if is_knowledge_raw in ("false", "0", "no"):
                is_knowledge = False
            elif is_knowledge_raw in ("true", "1", "yes"):
                is_knowledge = True
            else:
                is_knowledge = doc_domain not in (
                    "EVALUATION_DATA",
                    "USER_PERSONA",
                    "SYSTEM_CONFIGURATION",
                    "OTHER",
                )
            sensitivity = (row.get("sensitivity") or "").strip() or "INTERNAL"
            reason = (row.get("classification_reason") or "").strip()

            rows.append(



                RegistryRow(
                    source_file=row["source_file"],
                    document_domain=doc_domain,
                    related_departments=related_depts,
                    access_scope=access_scope,
                    authorized_departments=auth_depts,
                    authorized_roles=auth_roles,
                    authorization_status=auth_status,
                    authorization_source=auth_source,
                    classification_source=class_source,
                    is_knowledge_doc=is_knowledge,
                    department=(row.get("department") or "GENERAL").strip() or "GENERAL",
                    sensitivity=sensitivity,
                    access_category=access_category,
                    scope=scope,
                    issuer=issuer,
                    document_type=doc_type,
                    classification_confidence=conf,
                    classification_status=status,
                    classification_reason=reason,
                    category=row["category"],
                    status=row["status"],
                    processed_path=row["processed_path"],
                    chunks_path=row.get("chunks_path", ""),
                    indexed_at=row.get("indexed_at", ""),
                    source_type=row["source_type"],
                    is_official_policy=authority == "tenant_official_policy",
                    caveat=row.get("caveat", ""),
                    authority=authority,
                    provenance=provenance,
                    tenant=tenant,
                    publication_status=publication_status,
                    artifact_state=artifact_state,
                    retrieval_enabled=retrieval_enabled and is_knowledge,
                    expiry_date=expiry_date,
                )
            )
        return rows


def rag_eligible_rows(rows: list[RegistryRow]) -> list[RegistryRow]:
    """Điều kiện đủ để một tài liệu được chunk/index.
    Chỉ index những tài liệu KNOWLEDGE DOCUMENTS thực sự.
    Loại bỏ hoàn toàn SYSTEM / EVALUATION / CONFIGURATION data.
    """
    return [
        row
        for row in rows
        if row.status == "processed"
        and row.is_knowledge_doc
        and row.document_domain not in ("EVALUATION_DATA", "USER_PERSONA", "SYSTEM_CONFIGURATION", "OTHER")
        and row.source_type not in NON_RAG_SOURCE_TYPES
        and row.publication_status == "active"
        and row.retrieval_enabled
    ]



def update_registry_column(source_file: str, column: str, value: str, path: str = REGISTRY_PATH) -> None:
    """Ghi an toàn: đọc toàn bộ -> sửa 1 dòng -> ghi ra file tạm -> verify đọc lại -> os.replace.
    Tránh lặp lại sự cố crash-giữa-chừng làm hỏng registry đã gặp trước đó."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    found = False
    for row in rows:
        if row["source_file"] == source_file:
            row[column] = value
            found = True
    if not found:
        raise ValueError(f"source_file not found in registry: {source_file}")

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with open(tmp_path, encoding="utf-8") as f:
        if len(list(csv.DictReader(f))) != len(rows):
            raise RuntimeError("registry write verification failed, aborting replace")

    os.replace(tmp_path, path)
