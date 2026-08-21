#!/usr/bin/env python3
# ruff: noqa: E402
"""Ingest dataset Product qua đúng extractor/chunker/embedder/indexer hiện có.

Dataset nguồn chỉ được đọc. Registry, Markdown đã extract, chunks và report
được ghi dưới project P-153 để không thay đổi cấu trúc/nội dung dataset.

Chạy từ project root:
  python scripts/rag_pipeline/ingest_product.py --dataset-dir ../product_synthetic_dataset
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout.reconfigure(encoding="utf-8")

from src.config import get_settings
from src.ingestion.chunk_builder import build_chunks_from_text
from src.ingestion.embeddings import embed_batch, embed_texts
from src.ingestion.extractors.documents import extract_document
from src.ingestion.indexer import delete_by_source_stem, get_chroma_client, get_collection, upsert_chunks
from src.ingestion.metadata import Chunk
from src.retrieval.bm25 import BM25

DEPARTMENT = "Product"
REGISTRY_FIELDS = [
    "source_file",
    "department",
    "category",
    "status",
    "processed_path",
    "chunks_path",
    "indexed_at",
    "source_type",
    "is_official_policy",
    "caveat",
    "authority",
    "provenance",
    "tenant",
    "publication_status",
    "artifact_state",
    "retrieval_enabled",
    "expiry_date",
    "document_id",
    "relative_path",
]
SMOKE_QUERIES = [
    {
        "question": "Checkout Redesign dự kiến release khi nào?",
        "expected_sources": {"PRD_Checkout_Redesign.pdf", "Product_Roadmap_Q4_2026.xlsx", "Release_Plan_October.xlsx"},
    },
    {
        "question": "Checkout Redesign đang có blocker gì?",
        "expected_sources": {"PRD_Checkout_Redesign.pdf", "Sprint_Planning_12.docx"},
    },
    {
        "question": "Recommendation System hiện ở trạng thái nào?",
        "expected_sources": {"PRD_Recommendation_System.docx", "Product_Weekly_Recommendation.pdf", "Product_Roadmap_Q4_2026.xlsx"},
    },
    {
        "question": "Kết quả experiment của Checkout Redesign là gì?",
        "expected_sources": {"Checkout_Experiment_Report.pdf"},
    },
]


def atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def atomic_write_registry(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, path)


def load_manifest(dataset_dir: str) -> list[dict]:
    manifest_path = os.path.join(dataset_dir, "metadata", "manifest.csv")
    with open(manifest_path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"Manifest rỗng: {manifest_path}")
    return rows


def meaningful_text(content: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    without_separators = re.sub(r"(?m)^\s*(?:---+|#+\s*[^\n]*)\s*$", "", without_comments)
    return without_separators.strip()


def product_where() -> dict:
    return {
        "$and": [
            {"department": DEPARTMENT},
            {"authority": "tenant_official_policy"},
            {"publication_status": "active"},
            {"artifact_state": "frozen"},
            {"retrieval_enabled": True},
        ]
    }


def smoke_retrieval(collection, settings) -> list[dict]:
    results: list[dict] = []
    for case in SMOKE_QUERIES:
        vector = embed_batch(
            [f"query: {case['question']}"],
            model=settings.embedding_model,
            base_url=settings.fpt_base_url,
            api_key=settings.fpt_api_key,
        )[0]
        raw = collection.query(
            query_embeddings=[vector],
            n_results=5,
            where=product_where(),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for chunk_id, metadata, distance in zip(
            (raw.get("ids") or [[]])[0],
            (raw.get("metadatas") or [[]])[0],
            (raw.get("distances") or [[]])[0],
        ):
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "source_file": metadata.get("source_file"),
                    "page_start": metadata.get("page_start"),
                    "sheet_start": metadata.get("sheet_start"),
                    "distance": round(float(distance), 6),
                }
            )
        found_sources = {hit["source_file"] for hit in hits}
        results.append(
            {
                "question": case["question"],
                "expected_source_hit": bool(found_sources & case["expected_sources"]),
                "hits": hits,
            }
        )
    return results


def lexical_smoke_retrieval(chunks: list[Chunk]) -> list[dict]:
    """Fallback chẩn đoán local khi embedding service chưa dùng được."""
    by_id = {chunk.metadata.chunk_id: chunk for chunk in chunks}
    index = BM25(list(by_id), [by_id[chunk_id].text for chunk_id in by_id])
    results: list[dict] = []
    for case in SMOKE_QUERIES:
        ranked = index.top_k(case["question"], k=5)
        hits = []
        for chunk_id, score in ranked:
            chunk = by_id[chunk_id]
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "source_file": chunk.metadata.source_file,
                    "page_start": chunk.metadata.page_start,
                    "sheet_start": chunk.metadata.sheet_start,
                    "bm25_score": round(float(score), 6),
                }
            )
        found_sources = {hit["source_file"] for hit in hits}
        results.append(
            {
                "question": case["question"],
                "expected_source_hit": bool(found_sources & case["expected_sources"]),
                "hits": hits,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        default=os.environ.get("PRODUCT_DATASET_DIR", "../product_synthetic_dataset"),
        help="Root dataset Product (chỉ đọc)",
    )
    parser.add_argument("--output-dir", default="data/product", help="Nơi ghi processed/chunks/report")
    parser.add_argument("--registry", default="data/metadata/product_document_registry.csv")
    parser.add_argument("--collection", default=None, help="Mặc định dùng collection hiện tại")
    parser.add_argument("--force", action="store_true", help="Extract lại output đã tồn tại")
    parser.add_argument("--skip-index", action="store_true", help="Chỉ extract + chunk, không embed/index")
    parser.add_argument("--skip-retrieval", action="store_true", help="Không chạy 4 retrieval smoke tests")
    args = parser.parse_args()

    dataset_dir = os.path.abspath(args.dataset_dir)
    output_dir = os.path.abspath(args.output_dir)
    processed_dir = os.path.join(output_dir, "processed")
    chunks_dir = os.path.join(output_dir, "chunks")
    report_path = os.path.join(output_dir, "ingest_report.json")
    registry_path = os.path.abspath(args.registry)
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(chunks_dir, exist_ok=True)

    settings = get_settings()
    manifest = load_manifest(dataset_dir)
    registry_rows: list[dict] = []
    chunks_by_source: dict[str, list[Chunk]] = {}
    failures: list[dict] = []
    method_counts: Counter[str] = Counter()

    for item in manifest:
        source_file = item["filename"].strip()
        source_path = os.path.abspath(os.path.join(dataset_dir, item["relative_path"]))
        if os.path.commonpath([dataset_dir, source_path]) != dataset_dir or not os.path.isfile(source_path):
            failures.append({"source_file": source_file, "error": "source_missing_or_outside_dataset"})
            continue

        stem = os.path.splitext(source_file)[0]
        processed_path = os.path.join(processed_dir, f"{stem}.md")
        chunks_path = os.path.join(chunks_dir, f"{stem}.json")
        try:
            if os.path.exists(processed_path) and not args.force:
                with open(processed_path, encoding="utf-8") as handle:
                    content = handle.read()
                method = "cached"
            else:
                content, method = extract_document(source_path, processed_path)
            if not meaningful_text(content):
                raise RuntimeError("không trích xuất được nội dung có ý nghĩa")

            chunks = build_chunks_from_text(
                content,
                source_file=source_file,
                department=DEPARTMENT,
                category=item["document_type"].strip(),
                source_type="synthetic",
                is_official_policy=True,
                caveat="Dữ liệu Product mô phỏng dùng cho môi trường demo.",
                authority="tenant_official_policy",
                provenance="synthetic_demo",
                tenant="nexatech",
                publication_status="active",
                artifact_state="frozen",
                retrieval_enabled=True,
                settings=settings,
            )
            if not chunks:
                raise RuntimeError("0 chunk sau khi làm sạch")
            atomic_write_json(chunks_path, [chunk.model_dump() for chunk in chunks])
            chunks_by_source[source_file] = chunks
            method_counts[method] += 1
            status = "processed"
            error = ""
        except Exception as exc:  # noqa: BLE001 - cần báo cáo từng file và tiếp tục corpus
            status = "rejected"
            error = f"{type(exc).__name__}: {exc}"
            failures.append({"source_file": source_file, "error": error})
            # Không để placeholder OCR lỗi hoặc chunk từ lần chạy cũ bị hiểu
            # nhầm là tài liệu đã ingest thành công.
            for stale_path in (processed_path, chunks_path):
                if os.path.exists(stale_path):
                    os.remove(stale_path)
            processed_path = ""
            chunks_path = ""

        registry_rows.append(
            {
                "source_file": source_file,
                "department": DEPARTMENT,
                "category": item["document_type"].strip(),
                "status": status,
                "processed_path": processed_path.replace("\\", "/"),
                "chunks_path": chunks_path.replace("\\", "/"),
                "indexed_at": "",
                "source_type": "synthetic",
                "is_official_policy": "true",
                "caveat": error or "Dữ liệu Product mô phỏng dùng cho môi trường demo.",
                "authority": "tenant_official_policy",
                "provenance": "synthetic_demo",
                "tenant": "nexatech",
                "publication_status": "active",
                "artifact_state": "frozen",
                "retrieval_enabled": "true",
                "expiry_date": "9999-12-31",
                "document_id": item["document_id"].strip(),
                "relative_path": item["relative_path"].strip(),
            }
        )

    atomic_write_registry(registry_path, registry_rows)

    collection_name = args.collection or settings.chroma_collection_name
    vector_count = 0
    collection_count = None
    indexed_at = ""
    index_error = None
    retrieval_results: list[dict] = []
    if not args.skip_index and chunks_by_source:
        try:
            collection = get_collection(get_chroma_client(settings), collection_name)
            for source_file, chunks in chunks_by_source.items():
                embeddings = embed_texts(
                    [chunk.embedding_text for chunk in chunks],
                    model=settings.embedding_model,
                    base_url=settings.fpt_base_url,
                    api_key=settings.fpt_api_key,
                    batch_size=settings.embedding_batch_size,
                )
                for chunk in chunks:
                    chunk.metadata.embedding_model = settings.embedding_model
                delete_by_source_stem(collection, chunks[0].metadata.source_stem)
                upsert_chunks(collection, chunks, embeddings)
                vector_count += len(chunks)
                print(f"[indexed] {source_file}: {len(chunks)} vectors")
            indexed_at = datetime.now(UTC).isoformat()
            for row in registry_rows:
                if row["status"] == "processed":
                    row["indexed_at"] = indexed_at
            atomic_write_registry(registry_path, registry_rows)
            collection_count = collection.count()
            if not args.skip_retrieval:
                retrieval_results = smoke_retrieval(collection, settings)
        except Exception as exc:  # noqa: BLE001 - report lỗi credential/network thay vì mất kết quả extract
            index_error = f"{type(exc).__name__}: {exc}"
            print(f"[index-error] {index_error}")

    all_chunks = [chunk for chunks in chunks_by_source.values() for chunk in chunks]
    lexical_results = (
        lexical_smoke_retrieval(all_chunks)
        if index_error and not args.skip_retrieval and all_chunks
        else []
    )
    report = {
        "department": DEPARTMENT,
        "dataset_dir": dataset_dir.replace("\\", "/"),
        "registry": registry_path.replace("\\", "/"),
        "manifest_files": len(manifest),
        "files_read": len(chunks_by_source),
        "files_failed": len(failures),
        "failures": failures,
        "extract_methods": dict(method_counts),
        "chunk_count": len(all_chunks),
        "vector_count": vector_count,
        "collection": collection_name,
        "collection_count": collection_count,
        "embedding_model": settings.embedding_model if vector_count else None,
        "index_error": index_error,
        "metadata_department_valid": bool(all_chunks) and all(c.metadata.department == DEPARTMENT for c in all_chunks),
        "citation_locations": {
            "chunks_with_page": sum(c.metadata.page_start is not None for c in all_chunks),
            "chunks_with_sheet": sum(c.metadata.sheet_start is not None for c in all_chunks),
            "all_have_source": all(bool(c.metadata.source_file) for c in all_chunks),
        },
        "retrieval": retrieval_results,
        "retrieval_fallback_bm25": lexical_results,
        "indexed_at": indexed_at or None,
    }
    atomic_write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
