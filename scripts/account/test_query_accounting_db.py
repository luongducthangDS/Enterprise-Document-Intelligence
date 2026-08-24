#!/usr/bin/env python3
"""Script kiểm tra và truy vấn thử Chroma Cloud của phòng Kế toán.

Cách dùng:
    python scripts/test_query_accounting_db.py "Hạn mức duyệt chi của Giám đốc tài chính là bao nhiêu?"
"""

__test__ = False


import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client, get_collection
from src.services.fpt_client import embed_batch


def test_query(query_text: str, n_results: int = 3, collection_name: str | None = None):
    settings = get_settings()
    col_name = collection_name or "accounting_documents"

    print("=" * 80)
    print("🔍 KIỂM TRA TRUY VẤN CHROMA CLOUD (PHÒNG KẾ TOÁN)")
    print("=" * 80)
    print(f"❓ Câu hỏi truy vấn : '{query_text}'")
    print(f"🌐 Backend Vector DB: {settings.vector_db_backend}")
    print(f"📁 Collection       : {col_name}")

    # 1. Tính embedding câu hỏi
    print("\n🔢 Đang tính embedding câu hỏi...")
    query_emb = embed_batch(
        [f"query: {query_text}"],
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
    )[0]

    # 2. Truy vấn Chroma Cloud
    client = get_chroma_client(settings)
    collection = get_collection(client, col_name)

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    ids = results["ids"][0]
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    print(f"\n🎯 Tìm thấy {len(ids)} kết quả phù hợp nhất:")
    print("-" * 80)

    for rank, (chunk_id, doc, meta, dist) in enumerate(zip(ids, docs, metas, distances), start=1):
        similarity = 1.0 - dist  # Cosine similarity
        print(f"\n🏆 [KẾT QUẢ {rank}] - ID: {chunk_id} | Similarity: {similarity:.4f} (Distance: {dist:.4f})")
        print(f"   • Tiêu đề : {meta.get('title')}")
        print(f"   • File    : {meta.get('source_file')}")
        print(f"   • Mục     : {meta.get('heading_path') or '(Toàn văn)'}")
        print(f"   • Phân loại: {meta.get('category')}")
        print(f"   • Nội dung trích dẫn:")
        for line in doc.strip().splitlines():
            print(f"       | {line}")
        if len(doc.strip().splitlines()) > 5:
            print(f"       | ...")
        print("-" * 80)


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Quy định hạn mức chi tiêu và duyệt chi của công ty như thế nào?"
    test_query(query)
