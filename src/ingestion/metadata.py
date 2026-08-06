import csv
import os
from typing import Literal

from pydantic import BaseModel

REGISTRY_PATH = "data/metadata/document_registry.csv"

SourceType = Literal[
    "government_law",
    "official_policy",
    "public_template",
    "synthetic",
    "public_article",
    "eval_asset",
    "config",
    "rejected",
]

# source_type mà build_chunks phải bỏ qua — không phải nội dung RAG
NON_RAG_SOURCE_TYPES = {"eval_asset", "config", "rejected"}


class RegistryRow(BaseModel):
    source_file: str
    category: str
    status: str
    processed_path: str
    chunks_path: str = ""
    indexed_at: str = ""
    source_type: SourceType
    is_official_policy: bool
    caveat: str = ""


class ChunkMetadata(BaseModel):
    chunk_id: str
    source_file: str
    source_stem: str
    title: str
    category: str
    source_type: str
    is_official_policy: bool
    caveat: str = ""
    heading_path: str = ""
    chapter: str | None = None
    article: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_index: int
    char_count: int
    document_code: str | None = None
    version: str | None = None
    effective_date: str | None = None
    owner: str | None = None
    legal_basis: str | None = None
    embedding_model: str | None = None

    def to_chroma_metadata(self) -> dict:
        """Chroma chỉ chấp nhận giá trị metadata dạng str/int/float/bool — bỏ key None."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class Chunk(BaseModel):
    text: str
    embedding_text: str
    metadata: ChunkMetadata


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def load_registry(path: str = REGISTRY_PATH) -> list[RegistryRow]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [
            RegistryRow(
                source_file=row["source_file"],
                category=row["category"],
                status=row["status"],
                processed_path=row["processed_path"],
                chunks_path=row.get("chunks_path", ""),
                indexed_at=row.get("indexed_at", ""),
                source_type=row["source_type"],
                is_official_policy=_parse_bool(row["is_official_policy"]),
                caveat=row.get("caveat", ""),
            )
            for row in reader
        ]


def rag_eligible_rows(rows: list[RegistryRow]) -> list[RegistryRow]:
    return [
        row
        for row in rows
        if row.status == "processed" and row.source_type not in NON_RAG_SOURCE_TYPES
    ]


def update_registry_column(source_file: str, column: str, value: str, path: str = REGISTRY_PATH) -> None:
    """Ghi an toàn: đọc toàn bộ -> sửa 1 dòng -> ghi ra file tạm -> verify đọc lại -> os.replace.
    Tránh lặp lại sự cố crash-giữa-chừng làm hỏng registry đã gặp trước đó."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    found = False
    for row in rows:
        if row["source_file"] == source_file:
            row[column] = value
            found = True
    if not found:
        raise ValueError(f"source_file not found in registry: {source_file}")

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with open(tmp_path, encoding="utf-8") as f:
        if len(list(csv.DictReader(f))) != len(rows):
            raise RuntimeError("registry write verification failed, aborting replace")

    os.replace(tmp_path, path)
