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
# "government_law"/"official_policy"/"public_template"/"public_article" bị loại
# có chủ đích: sản phẩm chỉ trả lời bằng dữ liệu NỘI BỘ doanh nghiệp (thật hoặc
# synthetic đóng vai nội bộ khi chưa có tài liệu công ty thật). Luật, chính sách
# THẬT của doanh nghiệp khác (vd VinFast/Vingroup), template công khai không gắn
# công ty nào, và bài viết nghiệp vụ tham khảo đều không phải "chính sách của
# doanh nghiệp mình" — chỉ còn vai trò nguồn offline để soạn thêm tài liệu nội
# bộ, không phải nguồn agent được trích dẫn trực tiếp. Sau dòng này chỉ còn
# "synthetic" (V-NOVA, tenant_official_policy) là RAG-eligible.
NON_RAG_SOURCE_TYPES = {
    "eval_asset", "config", "rejected",
    "government_law", "official_policy", "public_template", "public_article",
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
    # "" = tài liệu không thuộc doanh nghiệp nào (luật, template, tham khảo).
    tenant: str = ""
    # Lifecycle (xem block comment ở PublicationStatus/ArtifactState phía trên).
    publication_status: str = DEFAULT_PUBLICATION_STATUS
    artifact_state: str = DEFAULT_ARTIFACT_STATE
    retrieval_enabled: bool = True
    expiry_date: str = NO_EXPIRY_SENTINEL


class ChunkMetadata(BaseModel):
    chunk_id: str
    source_file: str
    source_stem: str
    title: str
    category: str
    source_type: str
    is_official_policy: bool
    # authority/provenance/tenant: xem ghi chú taxonomy 2 chiều ở đầu file.
    # tenant="" nghĩa là tài liệu không thuộc doanh nghiệp nào — điều kiện cần
    # để agent KHÔNG được dùng nó trả lời câu hỏi "của doanh nghiệp mình".
    authority: str = "public_reference"
    provenance: str = "public_web"
    tenant: str = ""
    publication_status: str = DEFAULT_PUBLICATION_STATUS
    artifact_state: str = DEFAULT_ARTIFACT_STATE
    retrieval_enabled: bool = True
    expiry_date: str = NO_EXPIRY_SENTINEL
    # Bản số nguyên (YYYYMMDD) của effective_date/expiry_date, DÀNH RIÊNG cho
    # filter Chroma $lte/$gte (không nhận operand chuỗi) — xem date_to_ymd_int().
    # `effective_date` (chuỗi, field khác — có ở dưới, gán từ frontmatter) vẫn
    # giữ nguyên cho mục đích hiển thị/audit.
    effective_date_ymd: int = 1
    expiry_date_ymd: int = 99991231
    caveat: str = ""
    heading_path: str = ""
    chapter: str | None = None
    article: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_index: int
    char_count: int
    document_code: str | None = None
    version: str | None = None
    effective_date: str | None = None
    owner: str | None = None
    legal_basis: str | None = None
    embedding_model: str | None = None

    def to_chroma_metadata(self) -> dict:
        """Chroma chỉ chấp nhận giá trị metadata dạng str/int/float/bool — bỏ key None."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


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
            rows.append(
                RegistryRow(
                    source_file=row["source_file"],
                    category=row["category"],
                    status=row["status"],
                    processed_path=row["processed_path"],
                    chunks_path=row.get("chunks_path", ""),
                    indexed_at=row.get("indexed_at", ""),
                    source_type=row["source_type"],
                    # KHÔNG đọc cột is_official_policy của CSV nữa: sau khi tách
                    # taxonomy, "chính thức" chỉ còn một nghĩa duy nhất là "chính
                    # sách của tenant đang phục vụ". Giữ hai nguồn sự thật cho
                    # cùng một khái niệm là cách chắc chắn nhất để chúng lệch nhau.
                    is_official_policy=authority == "tenant_official_policy",
                    caveat=row.get("caveat", ""),
                    authority=authority,
                    provenance=provenance,
                    tenant=tenant,
                    publication_status=publication_status,
                    artifact_state=artifact_state,
                    retrieval_enabled=retrieval_enabled,
                    expiry_date=expiry_date,
                )
            )
        return rows


def rag_eligible_rows(rows: list[RegistryRow]) -> list[RegistryRow]:
    """Điều kiện đủ để một tài liệu được chunk/index. Lifecycle
    (publication_status/retrieval_enabled) là lớp chặn thứ hai NGOÀI
    source_type — cùng một tài liệu tenant_official_policy có thể tạm ngừng
    RAG (retrieval_enabled=False) hoặc bị supersede (publication_status khác
    "active") mà không cần đổi source_type/authority."""
    return [
        row
        for row in rows
        if row.status == "processed"
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
