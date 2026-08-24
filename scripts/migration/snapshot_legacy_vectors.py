#!/usr/bin/env python3
"""Công cụ Snapshot Dữ liệu Vector Hiện hữu (Read-Only Tool).

Nhiệm vụ:
1. Đọc toàn bộ vectors (IDs, metadatas, documents) từ collection legacy 'hr_documents' trên Chroma Cloud.
2. Lưu bản sao lưu offline an toàn vào 'storage/backups/snapshot_hr_documents_legacy.json'.
3. TUYỆT ĐỐI KHÔNG thực hiện bất kỳ thao tác sửa đổi hay xóa dữ liệu nào trên Chroma Cloud.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection


def create_legacy_snapshot(output_path: str = "storage/backups/snapshot_hr_documents_legacy.json") -> dict:
    settings = get_settings()
    client = get_chroma_client(settings)
    collection_name = settings.chroma_collection_name

    print(f"[Snapshot] Đang kết nối tới collection '{collection_name}' trên Chroma...")
    collection = get_collection(client, collection_name)
    total_count = collection.count()
    print(f"[Snapshot] Tìm thấy {total_count} vectors trong collection '{collection_name}'.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Đọc dữ liệu theo batch an toàn (100 items/batch để tuân thủ quota limit của Chroma Cloud)
    batch_size = 100
    all_ids = []
    all_metadatas = []
    all_documents = []
    all_embeddings = []

    offset = 0
    while offset < total_count:
        limit = min(batch_size, total_count - offset)
        res = collection.get(
            limit=limit,
            offset=offset,
            include=["metadatas", "documents", "embeddings"],
        )
        fetched_ids = res.get("ids", [])
        if not fetched_ids:
            break
        all_ids.extend(fetched_ids)
        all_metadatas.extend(res.get("metadatas", []))
        all_documents.extend(res.get("documents", []))
        fetched_embeddings = res.get("embeddings")
        if fetched_embeddings is not None and len(fetched_embeddings) > 0:
            all_embeddings.extend(fetched_embeddings)
        offset += len(fetched_ids)
        print(f"  • Đã đọc {offset}/{total_count} vectors (kèm embeddings 1024d)...")

    snapshot_data = {
        "metadata": {
            "source_collection": collection_name,
            "total_vectors": len(all_ids),
            "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
            "chroma_backend": settings.vector_db_backend,
            "embedding_available": True,
            "embedding_dimension": len(all_embeddings[0]) if len(all_embeddings) > 0 else 0,
            "schema_version": "legacy_v1",
            "migration_reason": "SINGLE_LEGACY_ENTERPRISE_DATASET",
            "status": "READ_ONLY_BACKUP",
        },
        "records": [
            {
                "id": cid,
                "document": doc,
                "metadata": meta,
                "embedding": emb.tolist() if hasattr(emb, "tolist") else emb,
            }
            for cid, doc, meta, emb in zip(all_ids, all_documents, all_metadatas, all_embeddings)
        ],
    }



    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

    print(f"\n[Snapshot THÀNH CÔNG] Đã lưu an toàn {len(all_ids)} vectors vào: {output_path}")
    return snapshot_data["metadata"]


if __name__ == "__main__":
    create_legacy_snapshot()
