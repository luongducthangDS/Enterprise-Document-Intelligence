#!/usr/bin/env python3
"""Export a complete, re-indexable Chroma collection bundle (read-only cloud)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    collection = get_chroma_client(get_settings()).get_collection(args.collection)
    response = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = response.get("ids") or []
    documents = response.get("documents") or []
    metadatas = response.get("metadatas") or []
    embeddings = response.get("embeddings")
    embeddings = embeddings.tolist() if hasattr(embeddings, "tolist") else list(embeddings or [])
    chunks = [
        {
            "text": text,
            "metadata": {**metadata, "chunk_id": chunk_id},
            "embedding": embedding,
            "embedding_dim": len(embedding),
        }
        for chunk_id, text, metadata, embedding in zip(ids, documents, metadatas, embeddings)
    ]
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_collection": args.collection,
        "total_chunks": len(chunks),
        "embedding_model": get_settings().embedding_model,
        "vector_dimension": len(embeddings[0]) if embeddings else 0,
        "chunks": chunks,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"collection": args.collection, "chunks": len(chunks), "out": str(output)}))


if __name__ == "__main__":
    main()
