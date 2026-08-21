import json
import os
import re

from src.config import Settings
from src.ingestion.chunkers import chunk_text
from src.ingestion.cleaners import clean_document, page_for_offset, sheet_for_offset
from src.ingestion.metadata import DEFAULT_EFFECTIVE_DATE, NO_EXPIRY_SENTINEL, Chunk, ChunkMetadata, date_to_ymd_int

H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def resolve_title(frontmatter: dict, text: str, stem: str) -> str:
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    m = H1_RE.search(text)
    if m:
        return m.group(1).strip()
    return stem


def normalize_tenant(value: str | None) -> str:
    """Chuẩn hoá tên công ty trong frontmatter thành slug tenant ổn định.

    Frontmatter ghi tên đầy đủ ("Công ty Cổ phần Tập đoàn NexaTech") nhưng
    tenant dùng để SO KHỚP (lọc "policy của doanh nghiệp mình") nên phải là
    khoá ổn định, không đổi khi tên pháp lý được viết khác đi.
    """
    if not value:
        return ""
    normalized = re.sub(r"(?i)\b(công ty|cổ phần|tập đoàn|tnhh|jsc|corp|inc)\b", " ", str(value))
    normalized = re.sub(r"[^0-9a-zA-ZÀ-ỹ]+", "-", normalized).strip("-").lower()
    return normalized


def build_chunks_from_text(
    raw_text: str,
    *,
    source_file: str,
    category: str,
    source_type: str,
    is_official_policy: bool,
    document_domain: str = "COMPANY_POLICY",
    related_departments: list[str] | str = "[]",
    access_scope: str = "COMPANY_WIDE",
    authorized_departments: list[str] | str = "[]",
    authorized_roles: list[str] | str = "[]",
    authorization_source: str = "BUSINESS_POLICY",
    classification_source: str = "DETERMINISTIC_AUDIT",
    department: str = "GENERAL",
    sensitivity: str = "INTERNAL",
    access_category: str = "COMPANY_POLICY",
    scope: str = "COMPANY_WIDE",
    issuer: str = "",
    document_type: str = "",
    owner: str | None = None,
    caveat: str = "",
    authority: str = "public_reference",
    provenance: str = "public_web",
    tenant: str = "",
    publication_status: str = "active",
    artifact_state: str = "frozen",
    retrieval_enabled: bool = True,
    expiry_date: str = NO_EXPIRY_SENTINEL,
    settings: Settings,
) -> list[Chunk]:
    cleaned = clean_document(raw_text)
    stem = os.path.splitext(source_file)[0]
    title = resolve_title(cleaned.frontmatter, cleaned.text, stem)
    resolved_tenant = tenant or normalize_tenant(cleaned.frontmatter.get("company"))

    text_chunks = chunk_text(
        cleaned.text,
        target_chars=settings.chunk_target_chars,
        max_chars=settings.chunk_max_chars,
        min_chars=settings.chunk_min_chars,
    )

    resolved_expiry_date = expiry_date or NO_EXPIRY_SENTINEL
    resolved_effective_date = (
        str(cleaned.frontmatter.get("effective_date")) if cleaned.frontmatter.get("effective_date") else None
    )
    effective_date_ymd = date_to_ymd_int(resolved_effective_date or DEFAULT_EFFECTIVE_DATE)
    expiry_date_ymd = date_to_ymd_int(resolved_expiry_date)

    # Parse related_departments (Semantic relevance recommendation only)
    parsed_related_depts: list[str] = []
    if isinstance(related_departments, list):
        parsed_related_depts = [str(d).upper().strip() for d in related_departments]
    elif isinstance(related_departments, str):
        try:
            parsed_related_depts = [str(d).upper().strip() for d in json.loads(related_departments)]
        except Exception:
            parsed_related_depts = [d.upper().strip() for d in related_departments.split(",") if d.strip()]

    # Parse authorized_departments (Actual authorization)
    parsed_auth_depts: list[str] = []
    if isinstance(authorized_departments, list):
        parsed_auth_depts = [str(d).upper().strip() for d in authorized_departments]
    elif isinstance(authorized_departments, str):
        try:
            parsed_auth_depts = [str(d).upper().strip() for d in json.loads(authorized_departments)]
        except Exception:
            parsed_auth_depts = [d.upper().strip() for d in authorized_departments.split(",") if d.strip()]

    # Parse authorized_roles (Actual authorization)
    parsed_auth_roles: list[str] = []
    if isinstance(authorized_roles, list):
        parsed_auth_roles = [str(r).upper().strip() for r in authorized_roles]
    elif isinstance(authorized_roles, str):
        try:
            parsed_auth_roles = [str(r).upper().strip() for r in json.loads(authorized_roles)]
        except Exception:
            parsed_auth_roles = [r.upper().strip() for r in authorized_roles.split(",") if r.strip()]

    chunks: list[Chunk] = []
    for idx, tc in enumerate(text_chunks):
        page_start = page_for_offset(cleaned.page_offsets, tc.start)
        page_end = page_for_offset(cleaned.page_offsets, max(tc.start, tc.end - 1))
        sheet_start = sheet_for_offset(cleaned.sheet_offsets, tc.start)
        sheet_end = sheet_for_offset(cleaned.sheet_offsets, max(tc.start, tc.end - 1))
        meta = ChunkMetadata(
            chunk_id=f"{stem}::{idx:04d}",
            source_file=source_file,
            source_stem=stem,
            title=title,
            document_domain=document_domain,
            related_departments=json.dumps(parsed_related_depts, ensure_ascii=False),
            access_scope=access_scope,
            authorized_departments=json.dumps(parsed_auth_depts, ensure_ascii=False),
            authorized_roles=json.dumps(parsed_auth_roles, ensure_ascii=False),
            authorization_source=authorization_source,
            classification_source=classification_source,
            department=department,
            sensitivity=sensitivity,
            access_category=access_category,
            scope=scope,
            issuer=issuer,
            document_type=document_type,
            category=category,
            source_type=source_type,
            is_official_policy=is_official_policy,
            authority=authority,
            provenance=provenance,
            tenant=resolved_tenant,
            publication_status=publication_status,
            artifact_state=artifact_state,
            retrieval_enabled=retrieval_enabled,
            expiry_date=resolved_expiry_date,
            effective_date_ymd=effective_date_ymd,
            expiry_date_ymd=expiry_date_ymd,
            caveat=caveat,
            heading_path=tc.heading_path,




            chapter=tc.chapter,
            article=tc.article,
            page_start=page_start,
            page_end=page_end,
            sheet_start=sheet_start,
            sheet_end=sheet_end,
            chunk_index=idx,
            char_count=len(tc.text),
            document_code=cleaned.frontmatter.get("document_code"),
            version=str(cleaned.frontmatter["version"]) if cleaned.frontmatter.get("version") is not None else None,
            effective_date=resolved_effective_date,
            owner=owner or cleaned.frontmatter.get("owner"),
            legal_basis=cleaned.frontmatter.get("legal_basis"),
        )
        breadcrumb = " — ".join(p for p in (title, tc.heading_path) if p)
        embedding_text = f"passage: {breadcrumb}\n\n{tc.text}" if breadcrumb else f"passage: {tc.text}"
        chunks.append(Chunk(text=tc.text, embedding_text=embedding_text, metadata=meta))

    return chunks
