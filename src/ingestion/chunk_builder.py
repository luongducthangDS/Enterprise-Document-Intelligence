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
from src.ingestion.cleaners import clean_document, page_for_offset
from src.ingestion.metadata import Chunk, ChunkMetadata

H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def resolve_title(frontmatter: dict, text: str, stem: str) -> str:
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    m = H1_RE.search(text)
    if m:
        return m.group(1).strip()
    return stem


def build_chunks_from_text(
    raw_text: str,
    *,
    source_file: str,
    category: str,
    source_type: str,
    is_official_policy: bool,
    caveat: str = "",
    settings: Settings,
) -> list[Chunk]:
    cleaned = clean_document(raw_text)
    stem = os.path.splitext(source_file)[0]
    title = resolve_title(cleaned.frontmatter, cleaned.text, stem)

    text_chunks = chunk_text(
        cleaned.text,
        target_chars=settings.chunk_target_chars,
        max_chars=settings.chunk_max_chars,
        min_chars=settings.chunk_min_chars,
    )

    chunks: list[Chunk] = []
    for idx, tc in enumerate(text_chunks):
        page_start = page_for_offset(cleaned.page_offsets, tc.start)
        page_end = page_for_offset(cleaned.page_offsets, max(tc.start, tc.end - 1))
        meta = ChunkMetadata(
            chunk_id=f"{stem}::{idx:04d}",
            source_file=source_file,
            source_stem=stem,
            title=title,
            category=category,
            source_type=source_type,
            is_official_policy=is_official_policy,
            caveat=caveat,
            heading_path=tc.heading_path,
            chapter=tc.chapter,
            article=tc.article,
            page_start=page_start,
            page_end=page_end,
            chunk_index=idx,
            char_count=len(tc.text),
            document_code=cleaned.frontmatter.get("document_code"),
            version=str(cleaned.frontmatter["version"]) if cleaned.frontmatter.get("version") is not None else None,
            effective_date=(
                str(cleaned.frontmatter.get("effective_date")) if cleaned.frontmatter.get("effective_date") else None
            ),
            owner=cleaned.frontmatter.get("owner"),
            legal_basis=cleaned.frontmatter.get("legal_basis"),
        )
        breadcrumb = " — ".join(p for p in (title, tc.heading_path) if p)
        embedding_text = f"passage: {breadcrumb}\n\n{tc.text}" if breadcrumb else f"passage: {tc.text}"
        chunks.append(Chunk(text=tc.text, embedding_text=embedding_text, metadata=meta))

    return chunks
