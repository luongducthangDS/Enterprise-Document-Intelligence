"""Index rebuild worker: nạp lại chunk đã có vào Chroma (finding #6).

Nguồn chunk là data/chunks/*.json — output của cả pipeline ngoại tuyến
(scripts/rag_pipeline/build_chunks.py) lẫn ingestion worker, nên rebuild không
phải parse lại tài liệu (đắt, và với PDF scan là gọi VLM lại).

Chiến lược:
- REPLACE / FULL: xoá hết vector cũ của tài liệu rồi upsert lại — dọn được chunk
  mồ côi khi số chunk giảm sau lần re-chunk.
- INCREMENTAL: chỉ upsert đè, không xoá — nhanh hơn, dùng khi chỉ thêm tài liệu.

Backend gọi bằng `source_file`; `document_id` chỉ đi kèm để agent trả lại đúng
id đó trong kết quả, agent không tra cứu DB của Backend.
"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os

from src.config import Settings, get_settings
from src.ingestion.embeddings import embed_texts
from src.ingestion.indexer import delete_by_source_stem, get_chroma_client, get_collection, upsert_chunks
from src.ingestion.metadata import Chunk
from src.models.schemas import IndexRebuildJobRequest
from src.workers.ingestion import chunks_dir
from src.workers.jobs import ProgressCallback

logger = logging.getLogger(__name__)


class IndexRebuildError(RuntimeError):
    """Lỗi nghiệp vụ của index rebuild — thông điệp trả thẳng cho Backend."""


def _load_chunks(path: str) -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        return [Chunk(**c) for c in json.load(f)]


def resolve_targets(request: IndexRebuildJobRequest, settings: Settings) -> list[tuple[str | None, str]]:
    """Trả về [(document_id, chunks_path)] theo đúng thứ tự Backend yêu cầu."""
    root = chunks_dir(settings)

    if not request.documents:
        paths = sorted(glob.glob(os.path.join(root, "*.json")))
        if not paths:
            raise IndexRebuildError(f"Không tìm thấy file chunk nào trong {root} để rebuild.")
        return [(None, p) for p in paths]

    targets: list[tuple[str | None, str]] = []
    missing: list[str] = []
    for target in request.documents:
        stem = os.path.splitext(os.path.basename(target.source_file.replace("\\", "/")))[0]
        path = os.path.join(root, f"{stem}.json")
        if not os.path.exists(path):
            missing.append(target.source_file)
            continue
        targets.append((target.document_id, path))

    if missing:
        raise IndexRebuildError(
            "Chưa có chunk cho tài liệu: " + ", ".join(missing) + " — cần chạy ingestion trước khi rebuild index."
        )
    return targets


def _reindex_one(chunks: list[Chunk], collection, settings: Settings, replace: bool) -> int:
    texts = [c.embedding_text for c in chunks]
    embeddings = embed_texts(
        texts,
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        batch_size=settings.embedding_batch_size,
    )
    for c in chunks:
        c.metadata.embedding_model = settings.embedding_model

    if replace:
        delete_by_source_stem(collection, chunks[0].metadata.source_stem)
    upsert_chunks(collection, chunks, embeddings)
    return len(chunks)


async def run_index_rebuild(
    request: IndexRebuildJobRequest,
    progress: ProgressCallback,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    targets = resolve_targets(request, settings)
    replace = request.strategy in ("REPLACE", "FULL")

    progress("PREPARING", 5)
    client = await asyncio.to_thread(get_chroma_client, settings)
    collection = await asyncio.to_thread(get_collection, client, settings.chroma_collection_name)

    documents: list[dict] = []
    total_vectors = 0
    for i, (document_id, path) in enumerate(targets):
        chunks = await asyncio.to_thread(_load_chunks, path)
        if not chunks:
            documents.append(
                {"document_id": document_id, "source_file": None, "chunk_count": 0, "skipped": "empty_chunks_file"}
            )
            continue

        vectors = await asyncio.to_thread(_reindex_one, chunks, collection, settings, replace)
        total_vectors += vectors
        documents.append(
            {
                "document_id": document_id,
                "source_file": chunks[0].metadata.source_file,
                "source_stem": chunks[0].metadata.source_stem,
                "chunk_count": vectors,
            }
        )
        # 5% khởi động + 90% cho vòng index, 5% còn lại cho bước đếm cuối.
        progress("INDEXING", 5 + int(90 * (i + 1) / len(targets)))

    collection_count = await asyncio.to_thread(collection.count)
    logger.info(
        "Index rebuild %s: %d tài liệu / %d vector, strategy=%s, collection=%s",
        request.job_id,
        len(documents),
        total_vectors,
        request.strategy,
        settings.chroma_collection_name,
    )
    return {
        "strategy": request.strategy,
        "documents": documents,
        "document_count": len(documents),
        "vector_count": total_vectors,
        "collection": settings.chroma_collection_name,
        "collection_count": collection_count,
        "embedding_model": settings.embedding_model,
        "active_index_version": settings.index_version,
    }
