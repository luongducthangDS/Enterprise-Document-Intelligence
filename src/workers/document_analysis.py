"""Analyse an uploaded document in an isolated staging index.

The staging collection is never queried by the production retrieval path.
Approval later re-runs normal ingestion against the official collection.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

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
from src.workers.ingestion import IngestionError, _load_content, _safe_source_file
from src.workers.jobs import ProgressCallback

MAX_REVIEW_TEXT_CHARS = 500_000
MAX_REVIEW_CHUNKS = 500


def _staging_collection_name(production_name: str) -> str:
    return f"{production_name}_staging"


def _get_staging_root(settings: Settings, tenant: str, submission_id: str) -> str:
    primary_root = os.path.join(settings.data_dir, "staging", tenant, submission_id)
    try:
        os.makedirs(primary_root, exist_ok=True)
        test_file = os.path.join(primary_root, ".perm_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return primary_root
    except (PermissionError, OSError):
        fallback_root = os.path.join(tempfile.gettempdir(), "p153_staging", tenant, submission_id)
        os.makedirs(fallback_root, exist_ok=True)
        return fallback_root


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
    root = _get_staging_root(settings, tenant, request.submission_id)
    raw_path = os.path.join(root, source_file)
    processed_path = os.path.join(root, f"{os.path.splitext(source_file)[0]}.md")
    with open(raw_path, "wb") as handle:
        handle.write(content)

    print(f"[DOC-ANALYSIS] File: {source_file}, Size: {len(content)} bytes, Dept: {request.department}, Tenant: {tenant}")
    try:
        text, method = extract_document(raw_path, processed_path)
        print(f"[DOC-ANALYSIS] Extracted {len(text)} chars via {method}")
    except UnsupportedDocumentError as exc:
        print(f"[DOC-ANALYSIS-ERROR] Unsupported format: {exc}")
        raise IngestionError(str(exc)) from exc
    if not text.strip():
        print("[DOC-ANALYSIS-ERROR] Extracted text is empty")
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
        print("[DOC-ANALYSIS-ERROR] No chunks generated")
        raise IngestionError("Tài liệu không tạo được đoạn nội dung nào sau khi làm sạch.")
    print(f"[DOC-ANALYSIS] Created {len(chunks)} chunks")

    progress("EMBEDDING", 65)
    from src.agents.llm import resolve_embedding_endpoint

    emb_model, emb_base_url, emb_api_key = resolve_embedding_endpoint()
    print(f"[DOC-ANALYSIS] Embedding {len(chunks)} chunks with model={emb_model}, base_url={emb_base_url}")
    for chunk in chunks:
        chunk.metadata.embedding_model = emb_model
        chunk.metadata.publication_status = "draft"
        chunk.metadata.artifact_state = "draft"
        chunk.metadata.retrieval_enabled = False
        chunk.metadata.authorization_status = "PENDING_REVIEW"

    progress("INDEXING_STAGING", 90)
    production_name = collection_name_for_chunks(chunks, settings)
    staging_name = _staging_collection_name(production_name)
    print(f"[DOC-ANALYSIS] Indexing staging into Chroma collection: {staging_name}")
    collection = get_collection(get_chroma_client(settings), staging_name)
    delete_by_source_stem(collection, staging_stem, tenant)
    batch_size = max(1, settings.embedding_batch_size)
    embedded = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = embed_texts(
            [chunk.embedding_text for chunk in batch],
            model=emb_model,
            base_url=emb_base_url,
            api_key=emb_api_key,
            batch_size=batch_size,
        )
        upsert_chunks(collection, batch, embeddings)
        embedded += len(batch)
    print(f"[DOC-ANALYSIS] Generated and indexed {embedded} embeddings successfully")
    print(f"[DOC-ANALYSIS] Staging index completed successfully: {staging_name}")

    warnings: list[str] = []
    preview_text = text
    if len(preview_text) > MAX_REVIEW_TEXT_CHARS:
        preview_text = preview_text[:MAX_REVIEW_TEXT_CHARS]
        warnings.append("Bản xem trước nội dung đã được rút gọn; toàn bộ tài liệu vẫn được đánh chỉ mục.")
    preview_chunks = chunks[:MAX_REVIEW_CHUNKS]
    if len(preview_chunks) < len(chunks):
        warnings.append("Danh sách đoạn xem trước đã được rút gọn; tổng số đoạn vẫn được giữ chính xác.")

    return {
        "submission_id": request.submission_id,
        "source_file": source_file,
        "extract_method": method,
        "character_count": len(text),
        "chunk_count": len(chunks),
        "extracted_text": preview_text,
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
            for chunk in preview_chunks
        ],
        "warnings": warnings,
    }


async def run_document_analysis(
    request: DocumentAnalysisJobRequest,
    progress: ProgressCallback,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    source_file = _safe_source_file(request.source_file)
    content = await _load_content(request)
    progress("EXTRACTING", 10)
    return await asyncio.to_thread(_analyse_and_index, request, source_file, content, progress, settings)
