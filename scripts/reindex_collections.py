#!/usr/bin/env python3
"""Index lại các collection đang chạy sang model embedding hiện tại (vd Gemini).

Không chạy lại ingestion: text + metadata đã có sẵn trong collection cũ, chỉ
tính lại vector rồi ghi vào `<tên cũ><CHROMA_COLLECTION_SUFFIX>`. Collection cũ
không bị sửa, nên quay lui chỉ cần bỏ suffix + đổi LLM_PROVIDER.
Chạy lại an toàn: chunk đã có ở collection đích thì bỏ qua.

    LLM_PROVIDER=gemini CHROMA_COLLECTION_SUFFIX=_gemini python scripts/reindex_collections.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agents.llm import resolve_embedding_endpoint  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.ingestion.embeddings import embed_texts  # noqa: E402
from src.ingestion.indexer import get_chroma_client  # noqa: E402

PAGE = 200


def main() -> None:
    settings = get_settings()
    suffix = settings.chroma_collection_suffix
    if not suffix:
        sys.exit("CHROMA_COLLECTION_SUFFIX rỗng: sẽ ghi đè collection đang chạy. Dừng.")
    model, base_url, api_key = resolve_embedding_endpoint()
    if "e5" in model.lower():
        sys.exit(f"Model embedding vẫn là {model}; đặt LLM_PROVIDER trước khi index lại.")

    client = get_chroma_client(settings)
    names = [settings.chroma_collection_name, settings.chroma_product_collection_name, settings.chroma_accounting_collection_name]
    for name in names:
        source = client.get_collection(name)
        target = client.get_or_create_collection(name=name + suffix, metadata={"hnsw:space": "cosine"})
        total, done, offset = source.count(), 0, 0
        while offset < total:
            page = source.get(include=["documents", "metadatas"], limit=PAGE, offset=offset)
            offset += PAGE
            existing = set(target.get(ids=page["ids"], include=[])["ids"])
            todo = [(i, d, m) for i, d, m in zip(page["ids"], page["documents"], page["metadatas"]) if i not in existing]
            if todo:
                ids, docs, metas = map(list, zip(*todo))
                vectors = embed_texts(docs, model=model, base_url=base_url, api_key=api_key, batch_size=50)
                target.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vectors)
                done += len(ids)
        print(f"{name} -> {name + suffix}: {total} chunk ({done} mới), đích có {target.count()}")


if __name__ == "__main__":
    main()
