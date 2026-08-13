import asyncio
import base64
from unittest.mock import AsyncMock, patch

import pytest

from src.config import get_settings
from src.workers.jobs import JobStore


def service_headers() -> dict[str, str]:
    token = get_settings().agent_service_token
    return {"X-Service-Token": token} if token else {}


@pytest.fixture
def job_store(tmp_path):
    """Store riêng cho từng test — không đụng vào storage/agent_jobs thật."""
    store = JobStore(str(tmp_path / "jobs"))
    with patch("src.api.routes.get_job_store", return_value=store):
        yield store


INGESTION_PAYLOAD = {
    "job_id": "job-ing-1",
    "document_id": "doc-1",
    "source_file": "policy.md",
    "content_base64": base64.b64encode("# Policy\n\nNội dung".encode()).decode(),
}


async def _wait_for_terminal(store: JobStore, job_id: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        record = store.get(job_id)
        if record and record.state in ("COMPLETED", "FAILED"):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job {job_id} không kết thúc trong {timeout}s")


@pytest.mark.asyncio
async def test_submit_ingestion_job_accepts_and_runs(client, job_store):
    runner = AsyncMock(return_value={"chunk_count": 7})
    with patch("src.api.routes.run_ingestion", new=runner):
        response = await client.post(
            "/api/v1/agent/jobs/ingestion", json=INGESTION_PAYLOAD, headers=service_headers()
        )
        assert response.status_code == 202
        assert response.json() == {
            "job_id": "job-ing-1",
            "kind": "INGESTION",
            "state": "QUEUED",
            "poll_after_ms": 1000,
        }
        await _wait_for_terminal(job_store, "job-ing-1")

    status_response = await client.get("/api/v1/agent/jobs/job-ing-1", headers=service_headers())
    body = status_response.json()
    assert status_response.status_code == 200
    assert body["state"] == "COMPLETED"
    assert body["progress_percent"] == 100
    assert body["result"] == {"chunk_count": 7}
    assert body["error"] is None


@pytest.mark.asyncio
async def test_job_failure_is_reported_with_error_message(client, job_store):
    runner = AsyncMock(side_effect=RuntimeError("FPT gateway 524"))
    with patch("src.api.routes.run_index_rebuild", new=runner):
        response = await client.post(
            "/api/v1/agent/jobs/index-rebuild",
            json={"job_id": "job-idx-1", "strategy": "REPLACE"},
            headers=service_headers(),
        )
        assert response.status_code == 202
        await _wait_for_terminal(job_store, "job-idx-1")

    body = (await client.get("/api/v1/agent/jobs/job-idx-1", headers=service_headers())).json()
    assert body["state"] == "FAILED"
    assert "FPT gateway 524" in body["error"]


@pytest.mark.asyncio
async def test_duplicate_job_id_returns_conflict(client, job_store):
    release = asyncio.Event()

    async def slow_runner(request, progress):
        await release.wait()
        return {}

    with patch("src.api.routes.run_evaluation", new=slow_runner):
        payload = {"job_id": "job-eval-1", "dataset_id": "evalset_hr_v1"}
        first = await client.post("/api/v1/agent/jobs/evaluation", json=payload, headers=service_headers())
        second = await client.post("/api/v1/agent/jobs/evaluation", json=payload, headers=service_headers())
        assert first.status_code == 202
        assert second.status_code == 409

        release.set()
        await _wait_for_terminal(job_store, "job-eval-1")


@pytest.mark.asyncio
async def test_unknown_job_returns_404(client, job_store):
    response = await client.get("/api/v1/agent/jobs/khong-ton-tai", headers=service_headers())
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/agent/jobs/ingestion", INGESTION_PAYLOAD),
        ("post", "/api/v1/agent/jobs/index-rebuild", {"job_id": "job-idx-2"}),
        ("post", "/api/v1/agent/jobs/evaluation", {"job_id": "job-eval-2"}),
        ("get", "/api/v1/agent/jobs/job-eval-2", None),
    ],
)
async def test_worker_endpoints_require_service_token(client, job_store, method, path, payload):
    settings = type("Settings", (), {"agent_service_token": "expected-token"})()
    with patch("src.api.routes.get_settings", return_value=settings):
        if method == "post":
            response = await client.post(path, json=payload, headers={"X-Service-Token": "wrong-token"})
        else:
            response = await client.get(path, headers={"X-Service-Token": "wrong-token"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_evaluation_job_validates_payload(client, job_store):
    response = await client.post(
        "/api/v1/agent/jobs/evaluation",
        json={"job_id": "job-eval-3", "limit": 0},
        headers=service_headers(),
    )
    assert response.status_code == 422
