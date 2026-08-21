#!/usr/bin/env python3
"""Chunk toàn bộ tài liệu processed đủ điều kiện RAG (theo document_registry.csv)
thành data/chunks/<stem>.json, và cập nhật cột chunks_path trong registry.

Chạy: python scripts/rag_pipeline/build_chunks.py [--force] [--only file1.md file2.md ...]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.chunk_builder import build_chunks_from_text
from src.ingestion.metadata import Chunk, load_registry, rag_eligible_rows, update_registry_column

OUT_DIR = "data/chunks"


def atomic_write_json(path: str, data) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def build_chunks_for_doc(row, settings) -> list[Chunk]:
    with open(row.processed_path, encoding="utf-8") as f:
        raw_text = f.read()

    return build_chunks_from_text(
        raw_text,
        source_file=row.source_file,
        document_domain=getattr(row, "document_domain", "COMPANY_POLICY"),
        related_departments=getattr(row, "related_departments", "[]"),
        access_scope=getattr(row, "access_scope", "COMPANY_WIDE"),
        authorized_departments=getattr(row, "authorized_departments", "[]"),
        authorized_roles=getattr(row, "authorized_roles", "[]"),
        authorization_status=getattr(row, "authorization_status", "ACTIVE"),
        authorization_source=getattr(row, "authorization_source", "BUSINESS_POLICY"),
        classification_source=getattr(row, "classification_source", "DETERMINISTIC_AUDIT"),
        is_knowledge_doc=getattr(row, "is_knowledge_doc", True),
        department=row.department,
        sensitivity=getattr(row, "sensitivity", "INTERNAL"),
        access_category=row.access_category,
        scope=row.scope,
        issuer=row.issuer,
        document_type=row.document_type,
        category=row.category,
        source_type=row.source_type,
        is_official_policy=row.is_official_policy,
        caveat=row.caveat,
        authority=row.authority,
        provenance=row.provenance,
        tenant=row.tenant,
        publication_status=row.publication_status,
        artifact_state=row.artifact_state,
        retrieval_enabled=row.retrieval_enabled,
        expiry_date=row.expiry_date,
        settings=settings,
    )







def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Chunk lại kể cả đã có output")
    parser.add_argument("--only", nargs="*", help="Chỉ xử lý các source_file khớp tên (vd bo_luat_lao_dong.pdf)")
    parser.add_argument("--category", default=None, help="Chỉ xử lý các tài liệu thuộc category này (vd government_legal)")
    parser.add_argument("--registry", default=None, help="Registry CSV (mặc định data/metadata/document_registry.csv)")
    parser.add_argument("--out-dir", default=OUT_DIR, help="Thư mục output chunk")
    args = parser.parse_args()

    settings = get_settings()
    os.makedirs(args.out_dir, exist_ok=True)

    registry_path = args.registry or "data/metadata/document_registry.csv"
    rows = rag_eligible_rows(load_registry(registry_path))
    total_chunks = 0
    all_lens: list[int] = []
    warnings: list[str] = []

    for row in rows:
        if args.category and row.category != args.category:
            continue
        if args.only and row.source_file not in args.only:
            continue

        stem = os.path.splitext(row.source_file)[0]
        out_path = os.path.join(args.out_dir, f"{stem}.json")

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
        update_registry_column(row.source_file, "chunks_path", out_path.replace("\\", "/"), path=registry_path)

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
