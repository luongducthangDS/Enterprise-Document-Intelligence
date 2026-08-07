import csv

import pytest

from src.ingestion.metadata import (
    ChunkMetadata,
    RegistryRow,
    load_registry,
    rag_eligible_rows,
    update_registry_column,
)

FIELDNAMES = [
    "source_file", "category", "status", "processed_path", "chunks_path",
    "indexed_at", "source_type", "is_official_policy", "caveat",
]

SAMPLE_ROWS = [
    {
        "source_file": "a.pdf", "category": "government_legal", "status": "processed",
        "processed_path": "data/processed/a.md", "chunks_path": "data/chunks/a.json",
        "indexed_at": "2026-08-05T00:00:00Z", "source_type": "government_law",
        "is_official_policy": "True", "caveat": "",
    },
    {
        "source_file": "b.md", "category": "compensation_policies", "status": "processed",
        "processed_path": "data/processed/b.md", "chunks_path": "",
        "indexed_at": "", "source_type": "synthetic",
        "is_official_policy": "false", "caveat": "Công ty giả định.",
    },
    {
        "source_file": "eval.json", "category": "eval_dataset", "status": "processed",
        "processed_path": "eval/datasets/eval.json", "chunks_path": "",
        "indexed_at": "", "source_type": "eval_asset",
        "is_official_policy": "False", "caveat": "",
    },
    {
        "source_file": "raw_only.pdf", "category": "government_legal", "status": "raw",
        "processed_path": "", "chunks_path": "", "indexed_at": "",
        "source_type": "government_law", "is_official_policy": "true", "caveat": "",
    },
]


def _write_registry(path, rows) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def registry_path(tmp_path):
    path = tmp_path / "document_registry.csv"
    _write_registry(path, SAMPLE_ROWS)
    return str(path)


class TestLoadRegistry:
    def test_parses_rows_and_bool_field(self, registry_path):
        rows = load_registry(registry_path)
        assert len(rows) == 4
        assert isinstance(rows[0], RegistryRow)
        assert rows[0].is_official_policy is True
        assert rows[1].is_official_policy is False
        assert rows[2].is_official_policy is False

    def test_missing_optional_columns_default_empty(self, registry_path):
        rows = load_registry(registry_path)
        b = next(r for r in rows if r.source_file == "b.md")
        assert b.chunks_path == ""
        assert b.indexed_at == ""


class TestRagEligibleRows:
    def test_filters_non_rag_source_types_and_non_processed(self, registry_path):
        rows = load_registry(registry_path)
        eligible = rag_eligible_rows(rows)
        eligible_files = {r.source_file for r in eligible}
        assert eligible_files == {"a.pdf", "b.md"}


class TestUpdateRegistryColumn:
    def test_updates_only_target_row(self, registry_path):
        update_registry_column("b.md", "indexed_at", "2026-08-05T01:00:00Z", path=registry_path)
        rows = load_registry(registry_path)
        b = next(r for r in rows if r.source_file == "b.md")
        a = next(r for r in rows if r.source_file == "a.pdf")
        assert b.indexed_at == "2026-08-05T01:00:00Z"
        assert a.indexed_at == "2026-08-05T00:00:00Z"  # không đụng dòng khác

    def test_raises_for_unknown_source_file(self, registry_path):
        with pytest.raises(ValueError):
            update_registry_column("khong_ton_tai.pdf", "indexed_at", "x", path=registry_path)

    def test_does_not_corrupt_file_on_error(self, registry_path):
        with pytest.raises(ValueError):
            update_registry_column("khong_ton_tai.pdf", "indexed_at", "x", path=registry_path)
        # File gốc vẫn đọc được nguyên vẹn sau khi update thất bại
        rows = load_registry(registry_path)
        assert len(rows) == 4


class TestChunkMetadataToChromaMetadata:
    def test_drops_none_values(self):
        meta = ChunkMetadata(
            chunk_id="a::0000",
            source_file="a.pdf",
            source_stem="a",
            title="Tài liệu A",
            category="government_legal",
            source_type="government_law",
            is_official_policy=True,
            heading_path="Chương I",
            chapter="Chương I",
            article=None,
            page_start=1,
            page_end=None,
            chunk_index=0,
            char_count=100,
        )
        out = meta.to_chroma_metadata()
        assert "article" not in out
        assert "page_end" not in out
        assert out["page_start"] == 1
        assert out["is_official_policy"] is True
        assert out["chunk_id"] == "a::0000"
