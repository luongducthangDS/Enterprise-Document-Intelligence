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
    return client.get_or_create_collection(name=name)


def delete_by_source_stem(collection: Collection, source_stem: str) -> None:
    """Xoá toàn bộ chunk cũ của 1 tài liệu trước khi upsert lại — tránh chunk mồ
    côi khi re-chunk làm lệch chunk_index so với lần index trước."""
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
