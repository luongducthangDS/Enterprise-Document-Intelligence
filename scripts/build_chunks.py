#!/usr/bin/env python3
"""Chunk toàn bộ tài liệu processed đủ điều kiện RAG (theo document_registry.csv)
thành data/chunks/<stem>.json, và cập nhật cột chunks_path trong registry.

Chạy: python scripts/build_chunks.py [--force] [--only file1.md file2.md ...]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.chunkers import chunk_text
from src.ingestion.cleaners import clean_document, page_for_offset
from src.ingestion.metadata import Chunk, ChunkMetadata, load_registry, rag_eligible_rows, update_registry_column

OUT_DIR = "data/chunks"
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def atomic_write_json(path: str, data) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def resolve_title(frontmatter: dict, text: str, stem: str) -> str:
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    m = H1_RE.search(text)
    if m:
        return m.group(1).strip()
    return stem


def build_chunks_for_doc(row, settings) -> list[Chunk]:
    with open(row.processed_path, encoding="utf-8") as f:
        raw_text = f.read()

    cleaned = clean_document(raw_text)
    stem = os.path.splitext(row.source_file)[0]
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
            source_file=row.source_file,
            source_stem=stem,
            title=title,
            category=row.category,
            source_type=row.source_type,
            is_official_policy=row.is_official_policy,
            caveat=row.caveat,
            heading_path=tc.heading_path,
            chapter=tc.chapter,
            article=tc.article,
            page_start=page_start,
            page_end=page_end,
            chunk_index=idx,
            char_count=len(tc.text),
            document_code=cleaned.frontmatter.get("document_code"),
            version=str(cleaned.frontmatter["version"]) if cleaned.frontmatter.get("version") is not None else None,
            effective_date=str(cleaned.frontmatter.get("effective_date")) if cleaned.frontmatter.get("effective_date") else None,
            owner=cleaned.frontmatter.get("owner"),
            legal_basis=cleaned.frontmatter.get("legal_basis"),
        )
        breadcrumb = " — ".join(p for p in (title, tc.heading_path) if p)
        embedding_text = f"{breadcrumb}\n\n{tc.text}" if breadcrumb else tc.text
        chunks.append(Chunk(text=tc.text, embedding_text=embedding_text, metadata=meta))

    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Chunk lại kể cả đã có output")
    parser.add_argument("--only", nargs="*", help="Chỉ xử lý các source_file khớp tên (vd bo_luat_lao_dong.pdf)")
    args = parser.parse_args()

    settings = get_settings()
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = rag_eligible_rows(load_registry())
    total_chunks = 0
    all_lens: list[int] = []
    warnings: list[str] = []

    for row in rows:
        if args.only and row.source_file not in args.only:
            continue

        stem = os.path.splitext(row.source_file)[0]
        out_path = os.path.join(OUT_DIR, f"{stem}.json")

        if os.path.exists(out_path) and not args.force and not args.only:
            print(f"[skip] {stem} — đã có chunks")
            continue

        if not os.path.exists(row.processed_path):
            print(f"[missing] {row.source_file} — processed_path không tồn tại: {row.processed_path}")
            warnings.append(f"{row.source_file}: processed_path không tồn tại")
            continue

        chunks = build_chunks_for_doc(row, settings)
        if len(chunks) <= 1:
            warnings.append(f"{row.source_file}: chỉ tách được {len(chunks)} chunk — kiểm tra lại cấu trúc")

        atomic_write_json(out_path, [c.model_dump() for c in chunks])
        update_registry_column(row.source_file, "chunks_path", out_path.replace("\\", "/"))

        lens = [c.metadata.char_count for c in chunks]
        all_lens.extend(lens)
        total_chunks += len(chunks)
        print(f"[chunked] {stem}: {len(chunks)} chunks, len=[{min(lens) if lens else 0},{max(lens) if lens else 0}]")

    print()
    print(f"=== Tổng kết: {total_chunks} chunks từ {len(rows)} tài liệu ===")
    if all_lens:
        print(f"Kích thước chunk: min={min(all_lens)}, max={max(all_lens)}, avg={sum(all_lens)//len(all_lens)}")
    if warnings:
        print(f"\nCảnh báo ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
