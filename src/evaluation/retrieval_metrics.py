"""Pure helpers for keeping chunk-level and document-level eval consistent."""

from __future__ import annotations

import os
import unicodedata


def normalize_source_stem(source_file: str | None) -> str:
    """Normalize paths/extensions without destroying Vietnamese source names."""
    value = str(source_file or "").replace("\\", "/")
    stem = os.path.splitext(os.path.basename(value))[0]
    return unicodedata.normalize("NFC", stem).strip().casefold()


def qrel_source_stems(relevant: dict[str, int]) -> set[str]:
    """Derive authoritative document stems from canonical ``stem::chunk`` IDs."""
    return {
        normalize_source_stem(chunk_id.rsplit("::", 1)[0])
        for chunk_id in relevant
        if "::" in chunk_id and normalize_source_stem(chunk_id.rsplit("::", 1)[0])
    }


def declared_source_stems(item: dict) -> set[str]:
    """Read every legacy location used by retrieval datasets."""
    sources = list(item.get("source_files") or [])
    if item.get("source_file"):
        sources.append(item["source_file"])
    metadata_source = (item.get("metadata") or {}).get("source_file")
    if metadata_source:
        sources.append(metadata_source)
    return {stem for source in sources if (stem := normalize_source_stem(source))}


def expected_source_stems(item: dict, relevant: dict[str, int]) -> tuple[set[str], str]:
    """Prefer qrels, because chunk relevance is the metric's canonical label."""
    from_qrels = qrel_source_stems(relevant)
    if from_qrels:
        return from_qrels, "qrels"
    return declared_source_stems(item), "dataset"


def first_doc_hit_rank(expected_stems: set[str], chunk_source_files: list[str]) -> int:
    if not expected_stems:
        return 0
    for rank, source_file in enumerate(chunk_source_files, start=1):
        if normalize_source_stem(source_file) in expected_stems:
            return rank
    return 0
