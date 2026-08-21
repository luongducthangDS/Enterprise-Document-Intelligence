#!/usr/bin/env python3
"""Script đẩy toàn bộ vector và metadata của phòng Kế toán lên Chroma Cloud.

Các bước:
1. Đọc dữ liệu 152 chunks kèm embeddings từ `data/data_accounting/accounting_chunks_with_embeddings.json`.
2. Chuẩn hóa metadata (gán access_category="GENERAL", department="accounting", lifecycle frozen/active).
3. Kết nối Chroma Cloud qua CloudClient (sử dụng thông tin cấu hình trong .env / settings).
4. Upsert toàn bộ 152 chunks vào các collections:
   - hr_documents (collection mặc định trong settings)
   - tenant_nexatech_knowledge (collection kiến thức tenant chung)
   - accounting_documents (collection chuyên biệt kế toán)
5. Kiểm tra và in ra số lượng vector trên Chroma Cloud sau khi đẩy.
"""
import json
import os
import sys
from pathlib import Path

# Thêm workspace root vào sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

# Thiết lập stdout UTF-8 cho Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.ingestion.metadata import ChunkMetadata


def main():
    settings = get_settings()
    print("=" * 80)
    print("🚀 ĐẨY DỮ LIỆU PHÒNG KẾ TOÁN LÊN CHROMA CLOUD")
    print("=" * 80)
    print(f"• Backend              : {settings.vector_db_backend}")
    print(f"• Chroma Tenant        : {settings.chroma_cloud_tenant}")
    print(f"• Chroma Database      : {settings.chroma_cloud_database}")
    print(f"• Default Collection   : {settings.chroma_collection_name}")
    print("-" * 80)

    # 1. Đọc file JSON đã nhúng sẵn vector
    json_path = WORKSPACE_ROOT / "data" / "data_accounting" / "accounting_chunks_with_embeddings.json"
    if not json_path.exists():
        print(f"❌ Không tìm thấy file dữ liệu: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks_data = data.get("chunks", [])
    print(f"📦 Đã nạp thành công {len(chunks_data)} chunks từ file JSON.")

    # 2. Chuẩn hóa metadata, ids, embeddings, documents
    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for item in chunks_data:
        raw_meta = dict(item.get("metadata", {}))
        # Đảm bảo các thuộc tính bắt buộc cho Access Control & Provenance Filter
        if "access_category" not in raw_meta:
            raw_meta["access_category"] = "GENERAL"
        if "department" not in raw_meta:
            raw_meta["department"] = "accounting"
        if "scope" not in raw_meta:
            raw_meta["scope"] = "COMPANY_WIDE"
        if "publication_status" not in raw_meta:
            raw_meta["publication_status"] = "active"
        if "artifact_state" not in raw_meta:
            raw_meta["artifact_state"] = "frozen"
        if "retrieval_enabled" not in raw_meta:
            raw_meta["retrieval_enabled"] = True
        if "effective_date_ymd" not in raw_meta:
            raw_meta["effective_date_ymd"] = 20250101
        if "expiry_date_ymd" not in raw_meta:
            raw_meta["expiry_date_ymd"] = 99991231

        chunk_meta = ChunkMetadata(**raw_meta)
        clean_chroma_meta = chunk_meta.to_chroma_metadata()

        ids.append(chunk_meta.chunk_id)
        embeddings.append(item["embedding"])
        documents.append(item["text"])
        metadatas.append(clean_chroma_meta)

    # 3. Kết nối Chroma Cloud
    print("\n🌐 Đang kết nối tới Chroma Cloud...")
    client = get_chroma_client(settings)

    target_collections = [
        "accounting_documents",
        "tenant_nexatech_knowledge",
    ]

    for col_name in target_collections:
        print(f"\n📤 Đang đẩy {len(ids)} chunks vào collection '{col_name}' trên Chroma Cloud...")
        col = get_collection(client, col_name)
        
        # Upsert theo batch để đảm bảo ổn định đường truyền mạng
        BATCH_SIZE = 50
        for i in range(0, len(ids), BATCH_SIZE):
            end_idx = min(i + BATCH_SIZE, len(ids))
            col.upsert(
                ids=ids[i:end_idx],
                embeddings=embeddings[i:end_idx],
                documents=documents[i:end_idx],
                metadatas=metadatas[i:end_idx],
            )
            print(f"   ✓ Đã upsert {end_idx}/{len(ids)} chunks vào '{col_name}'")

        print(f"   -> Collection '{col_name}' hiện có tổng cộng: {col.count()} chunks.")

    print("\n" + "=" * 80)
    print("🎉 HOÀN THÀNH ĐẨY DỮ LIỆU PHÒNG KẾ TOÁN LÊN CHROMA CLOUD THÀNH CÔNG!")
    print("=" * 80)


if __name__ == "__main__":
    main()
