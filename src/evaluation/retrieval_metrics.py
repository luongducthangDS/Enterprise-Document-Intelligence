"""Pure helpers for keeping chunk-level and document-level eval consistent."""

from __future__ import annotations

import os
import unicodedata

SCOREABLE_TYPES = {"in_scope", "single_chunk", "multi_chunk"}


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


def live_index_alignment(
    dataset: list[dict],
    qrels: dict[str, dict[str, int]],
    available_chunk_ids: set[str],
    *,
    min_relevance: int = 2,
) -> dict:
    """Measure whether a benchmark can be scored against a concrete index.

    Retrieval quality and benchmark/index alignment are different quantities.
    If a gold chunk no longer exists, counting it as a retrieval miss silently
    penalizes the retriever for an impossible target.  This preflight keeps the
    two failure modes separate and makes stale qrels explicit.
    """
    scored_queries = 0
    qrel_chunk_ids: set[str] = set()
    unavailable_by_query: dict[str, list[str]] = {}
    partially_available_queries: list[str] = []
    fully_available_queries: list[str] = []
    queries_with_any_available = 0

    for item in dataset:
        if item.get("retired") or item.get("type") not in SCOREABLE_TYPES:
            continue
        item_id = str(item.get("id") or "")
        relevant = {
            chunk_id
            for chunk_id, score in (qrels.get(item_id) or {}).items()
            if int(score) >= min_relevance
        }
        if not relevant:
            continue
        scored_queries += 1
        qrel_chunk_ids.update(relevant)
        missing = sorted(relevant - available_chunk_ids)
        present = relevant & available_chunk_ids
        if present:
            queries_with_any_available += 1
        if missing:
            unavailable_by_query[item_id] = missing
            if present:
                partially_available_queries.append(item_id)
        else:
            fully_available_queries.append(item_id)

    present_qrel_ids = qrel_chunk_ids & available_chunk_ids
    unavailable_queries = sorted(unavailable_by_query)
    qrel_source_ids = qrel_source_stems({chunk_id: 2 for chunk_id in qrel_chunk_ids})
    index_source_ids = qrel_source_stems({chunk_id: 2 for chunk_id in available_chunk_ids})

    label_coverage = len(present_qrel_ids) / len(qrel_chunk_ids) if qrel_chunk_ids else 1.0
    query_coverage = queries_with_any_available / scored_queries if scored_queries else 1.0
    benchmark_valid = len(present_qrel_ids) == len(qrel_chunk_ids)
    return {
        "benchmark_valid": benchmark_valid,
        "scored_queries": scored_queries,
        "qrel_chunk_labels": len(qrel_chunk_ids),
        "available_qrel_chunk_labels": len(present_qrel_ids),
        "missing_qrel_chunk_labels": len(qrel_chunk_ids - available_chunk_ids),
        "qrel_chunk_label_coverage": round(label_coverage, 4),
        "queries_with_any_available_qrel": queries_with_any_available,
        "query_coverage": round(query_coverage, 4),
        "fully_available_queries": len(fully_available_queries),
        "partially_available_queries": sorted(partially_available_queries),
        "unavailable_queries": unavailable_queries,
        "missing_qrel_ids_by_query": unavailable_by_query,
        "index_chunk_count": len(available_chunk_ids),
        "index_source_count": len(index_source_ids),
        "qrel_source_count": len(qrel_source_ids),
        "available_qrel_sources": sorted(qrel_source_ids & index_source_ids),
        "missing_qrel_sources": sorted(qrel_source_ids - index_source_ids),
    }
