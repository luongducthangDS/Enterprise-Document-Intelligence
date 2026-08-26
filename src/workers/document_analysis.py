"""Analyse an uploaded document in an isolated staging index.

The staging collection is never queried by the production retrieval path.
Approval later re-runs normal ingestion against the official collection.
"""

from __future__ import annotations

import asyncio
import os

from src.config import Settings, get_settings
from src.ingestion.chunk_builder import build_chunks_from_text
from src.ingestion.embeddings import embed_texts
from src.ingestion.extractors.documents import UnsupportedDocumentError, extract_document
from src.ingestion.indexer import (
    collection_name_for_chunks,
    delete_by_source_stem,
    get_chroma_client,
    get_collection,
    upsert_chunks,
)
from src.models.schemas import DocumentAnalysisJobRequest
from src.security.tenant_resolver import validate_tenant_id
from src.workers.ingestion import IngestionError, _decode_content, _safe_source_file
from src.workers.jobs import ProgressCallback


def _staging_collection_name(production_name: str) -> str:
    return f"{production_name}_staging"


def _analyse_and_index(
    request: DocumentAnalysisJobRequest,
    source_file: str,
    content: bytes,
    progress: ProgressCallback,
    settings: Settings,
) -> dict:
    tenant = validate_tenant_id(request.tenant)
    staging_source_file = f"{request.submission_id}__{source_file}"
    staging_stem = os.path.splitext(staging_source_file)[0]
    root = os.path.join(settings.data_dir, "staging", tenant, request.submission_id)
    raw_path = os.path.join(root, source_file)
    processed_path = os.path.join(root, f"{os.path.splitext(source_file)[0]}.md")
    os.makedirs(root, exist_ok=True)
    with open(raw_path, "wb") as handle:
        handle.write(content)

    try:
        text, method = extract_document(raw_path, processed_path)
    except UnsupportedDocumentError as exc:
        raise IngestionError(str(exc)) from exc
    if not text.strip():
        raise IngestionError("Không trích xuất được văn bản nào từ file.")

    progress("CHUNKING", 40)
    chunks = build_chunks_from_text(
        text,
        source_file=staging_source_file,
        department=request.department,
        category=request.category,
        source_type=request.source_type,
        is_official_policy=request.is_official_policy,
        caveat=request.caveat,
        authority=request.authority,
        provenance=request.provenance,
        tenant=tenant,
        access_scope=request.access_scope,
        authorized_role=request.authorized_role,
        authorized_roles=[request.authorized_role] if request.authorized_role else [],
        owner_user_id=request.owner_user_id,
        authorization_source=request.authorization_source,
        publication_status="draft",
        artifact_state="draft",
        retrieval_enabled=False,
        expiry_date=request.expiry_date,
        settings=settings,
    )
    if not chunks:
        raise IngestionError("Tài liệu không tạo được đoạn nội dung nào sau khi làm sạch.")

    progress("EMBEDDING", 65)
    embeddings = embed_texts(
        [chunk.embedding_text for chunk in chunks],
        model=settings.embedding_model,
        base_url=settings.fpt_base_url,
        api_key=settings.fpt_api_key,
        batch_size=settings.embedding_batch_size,
    )
    for chunk in chunks:
        chunk.metadata.embedding_model = settings.embedding_model
        chunk.metadata.publication_status = "draft"
        chunk.metadata.artifact_state = "draft"
        chunk.metadata.retrieval_enabled = False
        chunk.metadata.authorization_status = "PENDING_REVIEW"

    progress("INDEXING_STAGING", 90)
    production_name = collection_name_for_chunks(chunks, settings)
    staging_name = _staging_collection_name(production_name)
    collection = get_collection(get_chroma_client(settings), staging_name)
    delete_by_source_stem(collection, staging_stem, tenant)
    upsert_chunks(collection, chunks, embeddings)

    return {
        "submission_id": request.submission_id,
        "source_file": source_file,
        "extract_method": method,
        "character_count": len(text),
        "chunk_count": len(chunks),
        "extracted_text": text,
        "staging_collection": staging_name,
        "staging_source_stem": staging_stem,
        "chunks": [
            {
                "chunk_index": chunk.metadata.chunk_index,
                "content": chunk.text,
                "heading_path": chunk.metadata.heading_path,
                "page_start": chunk.metadata.page_start,
                "page_end": chunk.metadata.page_end,
                "char_count": chunk.metadata.char_count,
            }
            for chunk in chunks
        ],
        "warnings": [],
    }


async def run_document_analysis(
    request: DocumentAnalysisJobRequest,
    progress: ProgressCallback,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    source_file = _safe_source_file(request.source_file)
    content = _decode_content(request.content_base64)
    progress("EXTRACTING", 10)
    return await asyncio.to_thread(_analyse_and_index, request, source_file, content, progress, settings)
