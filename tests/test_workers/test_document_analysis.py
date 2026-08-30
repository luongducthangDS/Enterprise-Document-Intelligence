import base64
from unittest.mock import patch

import pytest

from src.config import get_settings
from src.models.schemas import DocumentAnalysisJobRequest
from src.workers.document_analysis import run_document_analysis

SAMPLE = (
    "# Quy định làm việc từ xa\n\n"
    + "Nhân viên đăng ký trước ba ngày làm việc và chờ quản lý phê duyệt. " * 40
)


@pytest.mark.asyncio
async def test_analysis_indexes_only_draft_chunks_in_staging(tmp_path):
    settings = get_settings().model_copy(update={"data_dir": str(tmp_path / "data"), "embedding_batch_size": 2})
    request = DocumentAnalysisJobRequest(
        job_id="analysis-job-1",
        submission_id="submission-123",
        source_file="remote-work.md",
        content_base64=base64.b64encode(SAMPLE.encode()).decode(),
        category="HR_POLICY",
        department="HR",
        tenant="nexatech",
        owner_user_id="owner-1",
        publication_status="draft",
        artifact_state="draft",
        retrieval_enabled=False,
    )
    stages: list[tuple[str, int]] = []

    with (
        patch(
            "src.workers.document_analysis.embed_texts",
            side_effect=lambda texts, **kwargs: [[0.1, 0.2, 0.3] for _ in texts],
        ),
        patch("src.workers.document_analysis.get_chroma_client", return_value=object()),
        patch("src.workers.document_analysis.get_collection", return_value=object()) as get_collection,
        patch("src.workers.document_analysis.delete_by_source_stem"),
        patch("src.workers.document_analysis.upsert_chunks") as upsert,
    ):
        result = await run_document_analysis(
            request,
            lambda stage, percent: stages.append((stage, percent)),
            settings=settings,
        )

    assert result["submission_id"] == "submission-123"
    assert result["extracted_text"].startswith("# Quy định")
    assert result["chunk_count"] == len(result["chunks"]) > 0
    assert result["staging_collection"].endswith("_staging")
    assert get_collection.call_args.args[1].endswith("_staging")

    chunks = upsert.call_args.args[1]
    assert all(chunk.metadata.publication_status == "draft" for chunk in chunks)
    assert all(chunk.metadata.artifact_state == "draft" for chunk in chunks)
    assert all(chunk.metadata.retrieval_enabled is False for chunk in chunks)
    assert all(chunk.metadata.source_file.startswith("submission-123__") for chunk in chunks)
    assert upsert.call_count >= 2
    assert all(len(call.args[1]) <= 2 for call in upsert.call_args_list)
    assert ("INDEXING_STAGING", 90) in stages
