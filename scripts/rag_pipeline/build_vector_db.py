#!/usr/bin/env python3
"""Embed các chunk trong data/chunks/*.json và upsert vào ChromaDB (Chroma Cloud
mặc định, hoặc local storage/vector_db/ nếu VECTOR_DB_BACKEND=local), cập nhật
cột indexed_at trong document_registry.csv.

Chạy: python scripts/rag_pipeline/build_vector_db.py [--force] [--only file1.md file2.md ...]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.embeddings import embed_texts
from src.ingestion.indexer import delete_by_source_stem, get_chroma_client, get_collection, upsert_chunks
from src.ingestion.metadata import Chunk, load_registry, rag_eligible_rows, update_registry_column


def load_chunks(path: str) -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [Chunk(**c) for c in raw]


def main() -> None:
    parser = argparse.ArgumentParser(description="Chroma Vector DB Indexer với Safety Guardrails P0-A")
    parser.add_argument("--force", action="store_true", help="Index lại kể cả đã có indexed_at")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Yêu cầu xóa toàn bộ collection (BỊ KHÓA MẶC ĐỊNH — yêu cầu cờ admin --allow-destructive-reset-DANGEROUS)",
    )
    parser.add_argument(
        "--allow-destructive-reset-DANGEROUS",
        action="store_true",
        help="Cờ admin xác nhận đồng ý thực hiện xóa toàn bộ collection (bị cấm vĩnh viễn trên production)",
    )
    parser.add_argument("--only", nargs="*", help="Chỉ xử lý các source_file khớp tên")
    parser.add_argument("--category", default=None, help="Chỉ xử lý các tài liệu thuộc category này (vd government_legal)")
    parser.add_argument("--collection", default=None, help="Ghi đè tên collection (mặc định lấy từ config, dùng khi so sánh thực nghiệm 2 embedding model)")
    parser.add_argument("--model", default=None, help="Ghi đè embedding model (mặc định lấy từ config)")
    parser.add_argument("--skip-registry-update", action="store_true", help="Không ghi indexed_at vào registry (dùng cho chạy thử nghiệm/so sánh model)")
    parser.add_argument("--registry", default=None, help="Registry CSV (mặc định data/metadata/document_registry.csv)")
    args = parser.parse_args()

    settings = get_settings()
    collection_name = args.collection or settings.chroma_collection_name
    embedding_model = args.model or settings.embedding_model
    client = get_chroma_client(settings)

    if args.reset:
        from src.ingestion.indexer import safe_delete_collection
        try:
            safe_delete_collection(
                client,
                collection_name,
                allow_destructive=args.allow_destructive_reset_DANGEROUS,
            )
            print(f"[reset] Đã thực hiện admin reset collection '{collection_name}' an toàn.")
        except PermissionError as pe:
            print(f"\n[SAFETY BLOCKED] Thao tác reset bị từ chối bởi Safety Guardrail: {pe}\n")
            sys.exit(1)
        except Exception as e:
            print(f"[reset] Lỗi khi thực hiện reset collection: {e}")

    collection = get_collection(client, collection_name)



    registry_path = args.registry or "data/metadata/document_registry.csv"
    rows = [r for r in rag_eligible_rows(load_registry(registry_path)) if r.chunks_path]
    total_vectors = 0
    docs_done = 0

    for row in rows:
        if args.category and row.category != args.category:
            continue
        if args.only and row.source_file not in args.only:
            continue
        if row.indexed_at and not args.force and not args.only:
            print(f"[skip] {row.source_file} — đã index lúc {row.indexed_at}")
            continue
        if not os.path.exists(row.chunks_path):
            print(f"[missing] {row.source_file} — chunks_path không tồn tại: {row.chunks_path}")
            continue

        chunks = load_chunks(row.chunks_path)
        if not chunks:
            print(f"[empty] {row.source_file} — 0 chunk, bỏ qua")
            continue

        stem = chunks[0].metadata.source_stem
        texts = [c.embedding_text for c in chunks]
        embeddings = embed_texts(
            texts,
            model=embedding_model,
            base_url=settings.fpt_base_url,
            api_key=settings.fpt_api_key,
            batch_size=settings.embedding_batch_size,
        )
        for c in chunks:
            c.metadata.embedding_model = embedding_model

        delete_by_source_stem(collection, stem)
        upsert_chunks(collection, chunks, embeddings)

        if not args.skip_registry_update:
            indexed_at = datetime.now(timezone.utc).isoformat()
            update_registry_column(row.source_file, "indexed_at", indexed_at, path=registry_path)

        total_vectors += len(chunks)
        docs_done += 1
        print(f"[indexed] {stem}: {len(chunks)} vectors")

    print()
    print(f"=== Tổng kết: {total_vectors} vector từ {docs_done} tài liệu vào collection '{collection_name}' (model={embedding_model}) ===")
    print(f"Collection count hiện tại: {collection.count()}")


if __name__ == "__main__":
    main()
