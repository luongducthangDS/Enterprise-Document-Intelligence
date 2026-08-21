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
    def test_derives_taxonomy_from_legacy_source_type(self, registry_path):
        """Registry chưa có 3 cột mới vẫn phải nạp được — authority/provenance
        suy từ source_type, để code chạy được cả trước và sau khi migrate CSV."""
        rows = load_registry(registry_path)
        assert len(rows) == 4
        assert isinstance(rows[0], RegistryRow)
        law, synthetic = rows[0], rows[1]
        assert (law.authority, law.provenance, law.tenant) == ("government_law", "government_source", "")
        assert (synthetic.authority, synthetic.provenance) == ("tenant_official_policy", "synthetic_demo")
        assert synthetic.tenant == "nexatech"

    def test_is_official_policy_means_tenant_policy_only(self, registry_path):
        """Sau khi tách taxonomy, "chính thức" chỉ còn MỘT nghĩa: chính sách của
        tenant đang phục vụ. Văn bản luật là nguồn có thẩm quyền nhưng KHÔNG phải
        chính sách doanh nghiệp, nên cờ này phải False — kể cả khi cột CSV ghi
        "true" (cột đó nay chỉ còn giá trị lịch sử, không được đọc)."""
        rows = load_registry(registry_path)
        assert rows[0].source_type == "government_law"
        assert rows[0].is_official_policy is False
        assert rows[1].is_official_policy is True
        assert rows[2].is_official_policy is False

    def test_missing_optional_columns_default_empty(self, registry_path):
        rows = load_registry(registry_path)
        b = next(r for r in rows if r.source_file == "b.md")
        assert b.department == "HR"
        assert b.chunks_path == ""
        assert b.indexed_at == ""


class TestRagEligibleRows:
    def test_filters_non_rag_source_types_and_non_processed(self, registry_path):
        """b.md là dòng processed + source_type RAG-eligible duy nhất. a.pdf và
        raw_only.pdf đều bị loại vì source_type="government_law" — luật chỉ còn
        là nguồn offline để soạn tài liệu nội bộ, không phải nguồn agent trích
        dẫn trực tiếp (xem NON_RAG_SOURCE_TYPES); raw_only.pdf còn bị loại thêm
        vì status != "processed". eval.json bị loại vì source_type="eval_asset"."""
        rows = load_registry(registry_path)
        eligible = rag_eligible_rows(rows)
        eligible_files = {r.source_file for r in eligible}
        assert eligible_files == {"b.md"}


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
