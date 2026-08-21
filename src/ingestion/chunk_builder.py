"""Dựng danh sách Chunk (kèm metadata + embedding_text) từ 1 tài liệu processed.

Tách khỏi scripts/rag_pipeline/build_chunks.py để ingestion worker
(src/workers/ingestion.py) chunk file Backend upload lên bằng ĐÚNG logic đang
dùng cho corpus ngoại tuyến — chunk_id, breadcrumb, page mapping phải giống hệt,
nếu không citation/qrels/eval sẽ lệch giữa hai đường vào.
"""

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
    department: str = "HR",
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
    # `company` chỉ có trong frontmatter của tài liệu policy; ưu tiên tenant do
    # registry truyền vào (nguồn sự thật) và chỉ dùng frontmatter khi registry
    # bỏ trống, để một file lẻ không tự khai mình thuộc tenant khác.
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
            department=department,
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
