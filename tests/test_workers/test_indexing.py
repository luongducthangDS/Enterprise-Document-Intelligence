import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config import get_settings
from src.models.schemas import IndexRebuildJobRequest, IndexRebuildTarget
from src.workers.indexing import IndexRebuildError, resolve_targets, run_index_rebuild


def _chunk(stem: str, idx: int) -> dict:
    return {
        "text": f"Nội dung {idx}",
        "embedding_text": f"passage: Nội dung {idx}",
        "metadata": {
            "chunk_id": f"{stem}::{idx:04d}",
            "source_file": f"{stem}.md",
            "source_stem": stem,
            "title": stem,
            "category": "LEAVE",
            "source_type": "official_policy",
            "is_official_policy": True,
            "tenant": "nexatech",
            "chunk_index": idx,
            "char_count": 12,
        },
    }


@pytest.fixture
def settings(tmp_path):
    settings = get_settings().model_copy(update={"data_dir": str(tmp_path / "data")})
    chunks_root = os.path.join(settings.data_dir, "chunks", "nexatech")
    os.makedirs(chunks_root)
    for stem in ("policy_a", "policy_b"):
        with open(os.path.join(chunks_root, f"{stem}.json"), "w", encoding="utf-8") as f:
            json.dump([_chunk(stem, 0), _chunk(stem, 1)], f, ensure_ascii=False)
    return settings


def _noop_progress(stage: str, percent: int) -> None:
    return None


def test_resolve_targets_defaults_to_every_chunk_file(settings):
    request = IndexRebuildJobRequest(job_id="idx-1", tenant="nexatech")
    targets = resolve_targets(request, settings)
    assert [os.path.basename(path) for _doc_id, path in targets] == ["policy_a.json", "policy_b.json"]


def test_resolve_targets_keeps_backend_document_ids(settings):
    request = IndexRebuildJobRequest(
        job_id="idx-1",
        tenant="nexatech",
        documents=[IndexRebuildTarget(document_id="doc-b", source_file="policy_b.md")],
    )
    targets = resolve_targets(request, settings)
    assert len(targets) == 1
    assert targets[0][0] == "doc-b"


def test_resolve_targets_reports_documents_without_chunks(settings):
    request = IndexRebuildJobRequest(
        job_id="idx-1",
        tenant="nexatech",
        documents=[IndexRebuildTarget(document_id="doc-x", source_file="chua_ingest.md")],
    )
    with pytest.raises(IndexRebuildError, match="chua_ingest.md"):
        resolve_targets(request, settings)


def test_resolve_targets_errors_when_no_chunks_at_all(tmp_path):
    empty = get_settings().model_copy(update={"data_dir": str(tmp_path / "empty")})
    with pytest.raises(IndexRebuildError, match="Không tìm thấy file chunk"):
        resolve_targets(IndexRebuildJobRequest(job_id="idx-1", tenant="nexatech"), empty)


@pytest.mark.asyncio
async def test_run_index_rebuild_replaces_then_upserts(settings):
    collection = MagicMock()
    collection.count.return_value = 4
    embeddings = [[0.1, 0.2]] * 2

    with (
        patch("src.workers.indexing.get_chroma_client", return_value=SimpleNamespace()),
        patch("src.workers.indexing.get_collection", return_value=collection),
        patch("src.workers.indexing.embed_texts", return_value=embeddings) as embed,
        patch("src.workers.indexing.delete_by_source_stem") as delete,
        patch("src.workers.indexing.upsert_chunks") as upsert,
    ):
        result = await run_index_rebuild(IndexRebuildJobRequest(job_id="idx-1", tenant="nexatech"), _noop_progress, settings=settings)

    assert result["document_count"] == 2
    assert result["vector_count"] == 4
    assert result["collection_count"] == 4
    assert result["active_index_version"] == settings.index_version
    assert embed.call_count == 2
    assert [call.args[1] for call in delete.call_args_list] == ["policy_a", "policy_b"]
    assert upsert.call_count == 2


@pytest.mark.asyncio
async def test_incremental_strategy_does_not_delete_existing_vectors(settings):
    collection = MagicMock()
    collection.count.return_value = 4

    with (
        patch("src.workers.indexing.get_chroma_client", return_value=SimpleNamespace()),
        patch("src.workers.indexing.get_collection", return_value=collection),
        patch("src.workers.indexing.embed_texts", return_value=[[0.1, 0.2]] * 2),
        patch("src.workers.indexing.delete_by_source_stem") as delete,
        patch("src.workers.indexing.upsert_chunks"),
    ):
        request = IndexRebuildJobRequest(job_id="idx-2", tenant="nexatech", strategy="INCREMENTAL")
        result = await run_index_rebuild(request, _noop_progress, settings=settings)

    assert delete.call_count == 0
    assert result["strategy"] == "INCREMENTAL"
