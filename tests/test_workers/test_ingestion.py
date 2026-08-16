import base64
import json
import os
from unittest.mock import patch

import pytest

from src.config import get_settings
from src.models.schemas import IngestionJobRequest
from src.workers.ingestion import IngestionError, _safe_source_file, run_ingestion

SAMPLE_DOC = (
    "# Chính sách nghỉ phép V-NOVA\n\n"
    "## Điều 1. Số ngày nghỉ phép năm\n\n"
    + "Nhân viên chính thức được nghỉ 12 ngày phép có hưởng lương mỗi năm. " * 30
    + "\n\n## Điều 2. Thủ tục đăng ký\n\n"
    + "Đăng ký nghỉ phép trên hệ thống trước ít nhất 3 ngày làm việc. " * 30
)


@pytest.fixture
def settings(tmp_path):
    return get_settings().model_copy(update={"data_dir": str(tmp_path / "data")})


def _request(content: str = SAMPLE_DOC, source_file: str = "chinh_sach_nghi_phep.md") -> IngestionJobRequest:
    return IngestionJobRequest(
        job_id="job-ingest-1",
        document_id="doc-uuid-1",
        source_file=source_file,
        content_base64=base64.b64encode(content.encode()).decode(),
        category="LEAVE",
        source_type="official_policy",
        is_official_policy=True,
    )


def _noop_progress(stage: str, percent: int) -> None:
    return None


@pytest.mark.parametrize(
    "source_file",
    ["../../etc/passwd.md", "report.exe", "", "  "],
)
def test_safe_source_file_rejects_unsafe_or_unsupported_names(source_file):
    if source_file.strip() and source_file.endswith(".md"):
        # Trường hợp traversal: giữ lại đúng basename, không thoát thư mục.
        assert _safe_source_file(source_file) == "passwd.md"
        return
    with pytest.raises(IngestionError):
        _safe_source_file(source_file)


@pytest.mark.asyncio
async def test_run_ingestion_extracts_chunks_and_indexes(settings):
    with patch("src.workers.ingestion._index_chunks", side_effect=lambda chunks, s: len(chunks)) as indexer:
        result = await run_ingestion(_request(), _noop_progress, settings=settings)

    assert result["chunk_count"] > 1
    assert result["vector_count"] == result["chunk_count"]
    assert result["document_id"] == "doc-uuid-1"
    assert result["source_stem"] == "chinh_sach_nghi_phep"
    assert indexer.call_count == 1

    # Chunk được ghi ra đĩa để index rebuild dùng lại mà không phải parse lại.
    chunks_path = os.path.join(settings.data_dir, "chunks", "chinh_sach_nghi_phep.json")
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    assert len(chunks) == result["chunk_count"]
    assert chunks[0]["metadata"]["chunk_id"] == "chinh_sach_nghi_phep::0000"
    assert chunks[0]["metadata"]["category"] == "LEAVE"
    assert os.path.exists(os.path.join(settings.data_dir, "processed", "chinh_sach_nghi_phep.md"))


@pytest.mark.asyncio
async def test_run_ingestion_rejects_invalid_base64(settings):
    request = _request()
    request.content_base64 = "không-phải-base64!!"
    with pytest.raises(IngestionError, match="base64"):
        await run_ingestion(request, _noop_progress, settings=settings)


@pytest.mark.asyncio
async def test_run_ingestion_rejects_empty_content(settings):
    request = _request(content="   \n  ")
    with pytest.raises(IngestionError, match="rỗng"):
        await run_ingestion(request, _noop_progress, settings=settings)


@pytest.mark.asyncio
async def test_run_ingestion_rejects_unsupported_extension(settings):
    request = _request(source_file="bang_luong.csv")
    with pytest.raises(IngestionError, match="không hỗ trợ"):
        await run_ingestion(request, _noop_progress, settings=settings)
