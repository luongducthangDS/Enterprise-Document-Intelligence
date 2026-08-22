#!/usr/bin/env python3
"""Restore local processed/chunk artifacts from a verified live collection.

The command is read-only for Chroma and is intended for disaster recovery and
clean-workspace reproducibility. Embeddings stay in Chroma/bundles, not chunks.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import get_settings
from src.ingestion.indexer import get_chroma_client
from src.ingestion.metadata import Chunk, ChunkMetadata


def merge_overlap(parts: list[str]) -> str:
    merged = ""
    for part in parts:
        part = part.strip()
        if not merged:
            merged = part
            continue
        max_overlap = min(len(merged), len(part), 2000)
        overlap = 0
        for size in range(max_overlap, 39, -1):
            if merged.endswith(part[:size]):
                overlap = size
                break
        merged = merged.rstrip() + "\n\n" + part[overlap:].lstrip()
    return merged.strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--chunks-dir", default="data/chunks")
    args = parser.parse_args()

    collection = get_chroma_client(get_settings()).get_collection(args.collection)
    response = collection.get(include=["documents", "metadatas"])
    groups: dict[str, list[tuple[int, Chunk]]] = defaultdict(list)
    for chunk_id, text, metadata in zip(
        response.get("ids") or [],
        response.get("documents") or [],
        response.get("metadatas") or [],
    ):
        source_file = str(metadata.get("source_file") or "").strip()
        if not source_file:
            continue
        stem = Path(source_file).stem
        chunk_index = int(metadata.get("chunk_index") or len(groups[stem]))
        normalized = {
            **metadata,
            "chunk_id": chunk_id,
            "source_file": source_file,
            "source_stem": stem,
            "chunk_index": chunk_index,
            "char_count": len(text),
            "department": str(metadata.get("department") or "GENERAL"),
            "category": str(metadata.get("category") or "company_policy"),
            "source_type": str(metadata.get("source_type") or "synthetic"),
            "is_official_policy": bool(metadata.get("is_official_policy", True)),
            "effective_date_ymd": int(metadata.get("effective_date_ymd") or 1),
            "expiry_date_ymd": int(metadata.get("expiry_date_ymd") or 99991231),
        }
        allowed = set(ChunkMetadata.model_fields)
        chunk_meta = ChunkMetadata(**{key: value for key, value in normalized.items() if key in allowed})
        groups[stem].append(
            (
                chunk_index,
                Chunk(
                    text=text,
                    embedding_text=f"passage: {chunk_meta.title or stem}\n\n{text}",
                    metadata=chunk_meta,
                ),
            )
        )

    processed_dir = Path(args.processed_dir)
    chunks_dir = Path(args.chunks_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    total_chunks = 0
    for stem, indexed_chunks in sorted(groups.items()):
        chunks = [chunk for _, chunk in sorted(indexed_chunks)]
        total_chunks += len(chunks)
        (processed_dir / f"{stem}.md").write_text(
            merge_overlap([chunk.text for chunk in chunks]),
            encoding="utf-8",
        )
        (chunks_dir / f"{stem}.json").write_text(
            json.dumps([chunk.model_dump() for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps({"collection": args.collection, "documents": len(groups), "chunks": total_chunks}))


if __name__ == "__main__":
    main()
