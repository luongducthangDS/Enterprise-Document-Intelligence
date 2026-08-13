"""Ingestion worker: file Backend upload -> extract -> chunk -> embed -> Chroma.

Đây là phần EXECUTION của finding #5 trong bug report 13/08 (job ingestion kẹt
QUEUED vì không có worker nào chạy). Vòng đời job (QUEUED/PROCESSING/COMPLETED/
FAILED trong DB) vẫn do Backend sở hữu; agent chỉ nhận nội dung file, chạy đúng
pipeline đang dùng ngoại tuyến, rồi trả số liệu về.

Cố ý KHÔNG ghi data/metadata/document_registry.csv: registry là sổ tay của
corpus ngoại tuyến (do người biên tập kiểm soát), còn tài liệu upload qua admin
UI có nguồn sự thật riêng là bảng `documents` bên Backend. Trộn hai sổ vào nhau
sẽ tạo hai chủ sở hữu cho cùng một dữ liệu.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os

from src.config import Settings, get_settings
from src.ingestion.chunk_builder import build_chunks_from_text
from src.ingestion.embeddings import embed_texts
from src.ingestion.extractors.documents import (
    SUPPORTED_EXTENSIONS,
    UnsupportedDocumentError,
    extract_document,
)
from src.ingestion.indexer import delete_by_source_stem, get_chroma_client, get_collection, upsert_chunks
from src.ingestion.metadata import Chunk
from src.models.schemas import IngestionJobRequest
from src.workers.jobs import ProgressCallback

logger = logging.getLogger(__name__)

# Cùng hạn mức với Backend (backend/app/services/document_service.py) — agent tự
# chặn lần nữa vì nó là tiến trình thật sự phải nuốt file.
MAX_FILE_BYTES = 25 * 1024 * 1024


class IngestionError(RuntimeError):
    """Lỗi nghiệp vụ của ingestion — thông điệp trả thẳng cho Backend."""


def upload_dir(settings: Settings) -> str:
    return os.path.join(settings.data_dir, "raw", "uploads")


def processed_dir(settings: Settings) -> str:
    return os.path.join(settings.data_dir, "processed")


def chunks_dir(settings: Settings) -> str:
    return os.path.join(settings.data_dir, "chunks")


def _atomic_write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _decode_content(content_base64: str) -> bytes:
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise IngestionError(f"content_base64 không phải base64 hợp lệ: {exc}") from exc
    if not content.strip():
        raise IngestionError("Nội dung file rỗng.")
    if len(content) > MAX_FILE_BYTES:
        raise IngestionError(f"File {len(content)} byte, vượt giới hạn {MAX_FILE_BYTES} byte.")
    return content


def _safe_source_file(source_file: str) -> str:
    """Chỉ lấy tên file: source_file đi thẳng vào đường dẫn ghi đĩa và vào
    chunk_id, không được chứa thành phần thư mục."""
    name = os.path.basename(source_file.replace("\\", "/")).strip()
    if not name or name in (".", ".."):
        raise IngestionError(f"source_file không hợp lệ: {source_file!r}")
    ext = os.path.splitext(name)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise IngestionError(f"Định dạng {ext or '(không có)'} không hỗ trợ. Chỉ nhận {', '.join(SUPPORTED_EXTENSIONS)}.")
    return name


def _index_chunks(chunks: list[Chunk], settings: Settings) -> int:
    """Embed + upsert (blocking — gọi qua asyncio.to_thread)."""
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

    client = get_chroma_client(settings)
    collection = get_collection(client, settings.chroma_collection_name)
    stem = chunks[0].metadata.source_stem
    delete_by_source_stem(collection, stem)
    upsert_chunks(collection, chunks, embeddings)
    return len(chunks)


async def run_ingestion(
    request: IngestionJobRequest,
    progress: ProgressCallback,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    source_file = _safe_source_file(request.source_file)
    stem = os.path.splitext(source_file)[0]

    progress("EXTRACTING", 10)
    content = _decode_content(request.content_base64)
    raw_path = os.path.join(upload_dir(settings), source_file)
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "wb") as f:
        f.write(content)

    processed_path = os.path.join(processed_dir(settings), f"{stem}.md")
    try:
        text, method = await asyncio.to_thread(extract_document, raw_path, processed_path)
    except UnsupportedDocumentError as exc:
        raise IngestionError(str(exc)) from exc
    if not text.strip():
        raise IngestionError("Không trích xuất được văn bản nào từ file (có thể là bản scan không đọc được).")

    progress("CHUNKING", 40)
    chunks = await asyncio.to_thread(
        build_chunks_from_text,
        text,
        source_file=source_file,
        category=request.category,
        source_type=request.source_type,
        is_official_policy=request.is_official_policy,
        caveat=request.caveat,
        settings=settings,
    )
    if not chunks:
        raise IngestionError("Tài liệu không tạo được chunk nào sau khi làm sạch.")

    chunks_path = os.path.join(chunks_dir(settings), f"{stem}.json")
    _atomic_write_json(chunks_path, [c.model_dump() for c in chunks])

    progress("EMBEDDING", 60)
    vector_count = await asyncio.to_thread(_index_chunks, chunks, settings)

    progress("INDEXING", 90)
    logger.info(
        "Ingestion job %s: %s -> %d chunk (%s), collection=%s",
        request.job_id,
        source_file,
        vector_count,
        method,
        settings.chroma_collection_name,
    )
    return {
        "document_id": request.document_id,
        "source_file": source_file,
        "source_stem": stem,
        "extract_method": method,
        "char_count": len(text),
        "chunk_count": len(chunks),
        "vector_count": vector_count,
        "chunks_path": chunks_path.replace("\\", "/"),
        "processed_path": processed_path.replace("\\", "/"),
        "collection": settings.chroma_collection_name,
        "embedding_model": settings.embedding_model,
        "index_version": settings.index_version,
    }
