#!/usr/bin/env python3
"""Script Chuyển đổi và Nạp Dữ liệu sang Tenant Collection Cô lập (Phase P0-C).

MỤC TIÊU:
1. Đọc 1.486 vectors từ snapshot offline 'storage/backups/snapshot_hr_documents_legacy.json'.
2. Ánh xạ định danh qua bảng deterministic 'data/metadata/migration_document_map.json'.
3. Gán namespace ID chuẩn: {tenant_slug}:{document_id}:{version_id}:{chunk_index:04d}.
4. Nạp vào collection cô lập: 'tenant_nexatech_knowledge'.
5. TUYỆT ĐỐI KHÔNG xóa/ghi đè/thay đổi collection 'hr_documents'.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.security.tenant_resolver import get_tenant_collection_name


def run_tenant_migration(
    snapshot_path: str = "storage/backups/snapshot_hr_documents_legacy.json",
    mapping_path: str = "data/metadata/migration_document_map.json",
    tenant_slug: str = "nexatech",
) -> dict:
    start_time = time.time()
    settings = get_settings()
    client = get_chroma_client(settings)

    target_collection_name = get_tenant_collection_name(tenant_slug)
    print(f"[Migration] Bắt đầu di chuyển dữ liệu sang collection: '{target_collection_name}'...")

    if not os.path.exists(snapshot_path):
        raise FileNotFoundError(f"Không tìm thấy snapshot file: {snapshot_path}")
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"Không tìm thấy mapping file: {mapping_path}")

    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    doc_map = mapping.get("documents", {})
    records = snapshot.get("records", [])
    print(f"[Migration] Nạp {len(records)} bản ghi từ snapshot...")

    target_collection = get_collection(client, target_collection_name)

    batch_size = 100
    transformed_ids = []
    transformed_docs = []
    transformed_metas = []
    transformed_embeddings = []

    # Chroma Cloud 32-key whitelist
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
        # New isolation & migration tracing fields
        "tenant_id",
        "document_id",
        "version_id",
        "chunk_index",
        "migration_source",
    }

    total_records = len(records)
    for i, record in enumerate(records):
        legacy_id = record["id"]
        doc_text = record["document"]
        legacy_meta = record["metadata"]
        embedding = record["embedding"]

        source_file = legacy_meta.get("source_file", "")
        doc_info = doc_map.get(source_file, {})

        document_id = doc_info.get("document_id") or "doc_legacy"
        version_id = doc_info.get("version_id") or "ver_legacy"
        tenant_id = doc_info.get("tenant_id") or "nexatech"

        # Lấy chunk_index từ legacy_id (format: {stem}::{index})
        chunk_idx = 0
        if "::" in legacy_id:
            try:
                chunk_idx = int(legacy_id.split("::")[-1])
            except ValueError:
                chunk_idx = i

        new_chunk_id = f"{tenant_slug}:{document_id}:{version_id}:{chunk_idx:04d}"

        new_meta = dict(legacy_meta)
        new_meta["tenant_id"] = tenant_id
        new_meta["document_id"] = document_id
        new_meta["version_id"] = version_id
        new_meta["chunk_index"] = chunk_idx
        new_meta["migration_source"] = "hr_documents_legacy"
        new_meta["tenant"] = tenant_slug

        filtered_meta = {k: v for k, v in new_meta.items() if k in CHROMA_ALLOWED_KEYS and v is not None}

        transformed_ids.append(new_chunk_id)
        transformed_docs.append(doc_text)
        transformed_metas.append(filtered_meta)
        transformed_embeddings.append(embedding)

    # Upsert theo batch vào target collection
    print(f"[Migration] Bắt đầu nạp vào Chroma Cloud '{target_collection_name}'...")
    for idx in range(0, total_records, batch_size):
        b_ids = transformed_ids[idx : idx + batch_size]
        b_docs = transformed_docs[idx : idx + batch_size]
        b_metas = transformed_metas[idx : idx + batch_size]
        b_embs = transformed_embeddings[idx : idx + batch_size]

        target_collection.upsert(
            ids=b_ids,
            embeddings=b_embs,
            documents=b_docs,
            metadatas=b_metas,
        )
        print(f"  • Đã nạp {min(idx + batch_size, total_records)}/{total_records} vectors...")

    target_count = target_collection.count()
    duration = time.time() - start_time
    print(f"\n[Migration THÀNH CÔNG] Hoàn tất nạp {target_count} vectors vào '{target_collection_name}' trong {duration:.2f}s.")

    return {
        "target_collection": target_collection_name,
        "total_migrated": target_count,
        "duration_seconds": round(duration, 2),
        "source_snapshot": snapshot_path,
        "deterministic_mapping": mapping_path,
    }


if __name__ == "__main__":
    run_tenant_migration()
