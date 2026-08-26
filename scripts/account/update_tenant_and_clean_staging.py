"""Script cập nhật tenant = "nexatech" cho 152 chunks trong collection accounting_documents
và xóa bỏ collection thừa accounting_documents_staging trên Chroma Cloud.
"""

import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection


def update_local_json_files():
    print("=" * 80)
    print("[1] CẬP NHẬT TENANT = 'nexatech' TRONG CÁC FILE JSON LOCAL")
    print("=" * 80)

    json_paths = [
        WORKSPACE_ROOT / "data" / "data_accounting" / "db_hr" / "accounting_chunks_with_embeddings.json",
        WORKSPACE_ROOT / "data" / "data_accounting" / "process" / "accounting_chunks_with_embeddings.json",
    ]

    for jp in json_paths:
        if jp.exists():
            print(f"[*] Đang xử lý: {jp}")
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            chunks = data.get("chunks", [])
            modified_count = 0
            for c in chunks:
                if "metadata" in c:
                    old_t = c["metadata"].get("tenant")
                    if old_t != "nexatech":
                        c["metadata"]["tenant"] = "nexatech"
                        modified_count += 1

            with open(jp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"    ✓ Đã cập nhật {modified_count}/{len(chunks)} chunks với tenant='nexatech'")
        else:
            print(f"[-] Bỏ qua (không tồn tại): {jp}")


def update_chroma_and_delete_staging():
    print("\n" + "=" * 80)
    print("[2] CẬP NHẬT TENANT TRÊN CHROMA CLOUD VÀ XÓA ACCOUNTING_DOCUMENTS_STAGING")
    print("=" * 80)

    settings = get_settings()
    client = get_chroma_client(settings)

    # 1. Liệt kê collections hiện có
    existing_cols = [c.name for c in client.list_collections()]
    print(f"[*] Danh sách Collections hiện tại trên Chroma Cloud ({len(existing_cols)}):")
    for name in existing_cols:
        print(f"    - {name}")

    # 2. Cập nhật tenant='nexatech' trong collection accounting_documents
    col_name = settings.chroma_accounting_collection_name
    if col_name in existing_cols:
        col = get_collection(client, col_name)
        print(f"\n[*] Đang lấy dữ liệu từ collection '{col_name}' ({col.count()} chunks)...")
        chroma_data = col.get(include=["metadatas"])
        ids = chroma_data.get("ids", [])
        metadatas = chroma_data.get("metadatas", [])

        ALLOWED_CHROMA_KEYS = {
            "chunk_id", "source_file", "source_stem", "title", "department",
            "access_scope", "category", "source_type", "is_official_policy",
            "authority", "provenance", "tenant", "publication_status",
            "artifact_state", "retrieval_enabled", "effective_date_ymd",
            "expiry_date_ymd", "heading_path", "page_start", "page_end",
            "document_code", "document_id", "public_url"
        }

        updated_ids = []
        updated_metadatas = []
        for c_id, raw_meta in zip(ids, metadatas):
            meta = {k: v for k, v in raw_meta.items() if k in ALLOWED_CHROMA_KEYS and v is not None}
            meta["tenant"] = "nexatech"
            updated_ids.append(c_id)
            updated_metadatas.append(meta)

        if updated_ids:
            BATCH_SIZE = 50
            for i in range(0, len(updated_ids), BATCH_SIZE):
                end_i = min(i + BATCH_SIZE, len(updated_ids))
                col.update(
                    ids=updated_ids[i:end_i],
                    metadatas=updated_metadatas[i:end_i],
                )
            print(f"    ✓ Đã cập nhật tenant='nexatech' cho toàn bộ {len(updated_ids)} chunks trong '{col_name}'!")
    else:
        print(f"[!] Không tìm thấy collection '{col_name}'")

    # 3. Xóa collection thừa accounting_documents_staging (nếu có)
    staging_col_name = "accounting_documents_staging"
    if staging_col_name in existing_cols:
        print(f"\n[*] Đang tiến hành XÓA collection thừa '{staging_col_name}'...")
        client.delete_collection(staging_col_name)
        print(f"    ✓ Đã XÓA THÀNH CÔNG collection '{staging_col_name}' trên Chroma Cloud!")
    else:
        print(f"\n[-] Collection '{staging_col_name}' không tồn tại hoặc đã được xóa trước đó.")

    # 4. Kiểm tra lại danh sách collection còn lại
    remaining_cols = [c.name for c in client.list_collections()]
    print("\n" + "=" * 80)
    print(f"[*] Danh sách Collections sau khi dọn dẹp ({len(remaining_cols)}):")
    for name in remaining_cols:
        print(f"    ✓ {name}")

    # Lấy mẫu 1 chunk từ accounting_documents để xác nhận
    if col_name in remaining_cols:
        col = get_collection(client, col_name)
        sample = col.get(limit=1, include=["metadatas"])
        sample_meta = sample["metadatas"][0] if sample["metadatas"] else {}
        print("\n[*] Mẫu Metadata của 1 chunk sau khi cập nhật:")
        print(f"    - chunk_id    : {sample_meta.get('chunk_id')}")
        print(f"    - tenant      : {sample_meta.get('tenant')}")
        print(f"    - department  : {sample_meta.get('department')}")
        print(f"    - document_id : {sample_meta.get('document_id')}")
        print(f"    - public_url  : {sample_meta.get('public_url')}")
    print("=" * 80)


if __name__ == "__main__":
    update_local_json_files()
    update_chroma_and_delete_staging()
