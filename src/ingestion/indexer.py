import chromadb
from chromadb.api.models.Collection import Collection

from src.config import Settings
from src.ingestion.metadata import Chunk


def get_chroma_client(settings: Settings) -> chromadb.ClientAPI:
    """"cloud" (Chroma Cloud, dùng chung team + server) hoặc "local"
    (PersistentClient trên đĩa — chỉ dùng dev/test offline, KHÔNG sống được trên
    Render vì free/standard tier không có persistent disk)."""
    if settings.vector_db_backend == "cloud":
        return chromadb.CloudClient(
            tenant=settings.chroma_cloud_tenant,
            database=settings.chroma_cloud_database,
            api_key=settings.chroma_cloud_api_key,
        )
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_collection(client: chromadb.ClientAPI, name: str) -> Collection:
    # Không truyền embedding_function — embedding luôn tính thủ công qua
    # src/ingestion/embeddings.py rồi truyền trực tiếp vào add/upsert/query, để
    # Chroma không phụ thuộc phải hiểu đúng response shape của FPT.AI Marketplace.
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def safe_delete_collection(
    client: chromadb.ClientAPI,
    collection_name: str,
    allow_destructive: bool = False,
    environment_override: str | None = None,
) -> None:
    """Guardrail P0-A: Chặn việc xóa collection trừ khi có cờ admin tường minh
    và TUYỆT ĐỐI không được phép xóa trên môi trường PRODUCTION."""
    from src.config import get_settings
    settings = get_settings()
    env = environment_override or settings.app_env

    if env == "production":
        raise PermissionError(
            f"CRITICAL SAFETY GUARDRAIL: delete_collection('{collection_name}') is strictly PROHIBITED "
            "in PRODUCTION environment under any circumstances."
        )

    if not allow_destructive:
        raise PermissionError(
            f"CRITICAL SAFETY GUARDRAIL: Destructive collection deletion blocked for '{collection_name}'. "
            "Normal re-index operations must use selective document purging. "
            "If an administrative reset is genuinely required, pass explicit authorization."
        )

    client.delete_collection(collection_name)


from src.security.tenant_resolver import get_tenant_collection_name, validate_tenant_id


def collection_name_for_department(
    department: str,
    settings: Settings,
    tenant_id: str | None = None,
) -> str:
    """Map department to proper collection name with tenant namespace."""
    dept = (department or "").upper().strip()
    safe_tenant = validate_tenant_id(tenant_id) if tenant_id else (settings.active_tenant or "nexatech")
    if dept in ("ACCOUNTING", "FINANCE", "KE_TOAN", "TAI_CHINH"):
        return f"tenant_{safe_tenant}_accounting_documents" if safe_tenant else settings.chroma_collection_name
    return get_tenant_collection_name(safe_tenant)


def collection_name_for_chunks(
    chunks: list[Chunk],
    settings: Settings,
    tenant_id: str | None = None,
) -> str:
    """Determine tenant-scoped collection from chunks metadata."""
    if not chunks:
        return settings.chroma_collection_name
    first_chunk = chunks[0]
    dept = getattr(first_chunk.metadata, "department", "GENERAL") or "GENERAL"
    resolved_tenant = tenant_id or getattr(first_chunk.metadata, "tenant", "") or settings.active_tenant
    return collection_name_for_department(dept, settings, resolved_tenant)


def delete_by_source_stem(collection: Collection, source_stem: str, tenant_id: str | None = None) -> None:
    """Xóa toàn bộ chunk cũ của 1 tài liệu trước khi upsert lại —
    nếu có tenant_id, giới hạn phạm vi xóa bên trong tenant đó để không xóa chéo file trùng tên."""
    if tenant_id == "":
        raise ValueError("tenant_id cannot be an empty string for scoped deletion")
    if tenant_id:
        collection.delete(where={"$and": [{"source_stem": source_stem}, {"tenant": tenant_id}]})
    else:
        collection.delete(where={"source_stem": source_stem})


def upsert_chunks(collection: Collection, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError(f"chunks ({len(chunks)}) và embeddings ({len(embeddings)}) không khớp số lượng")
    collection.upsert(
        ids=[c.metadata.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[c.metadata.to_chroma_metadata() for c in chunks],
    )

