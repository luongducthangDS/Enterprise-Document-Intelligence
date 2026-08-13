import asyncio

import pytest

from src.workers.jobs import RESTART_ERROR, JobExistsError, JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(str(tmp_path / "jobs"))


async def _wait_for_terminal(store: JobStore, job_id: str, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        record = store.get(job_id)
        if record and record.state in ("COMPLETED", "FAILED"):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job {job_id} không kết thúc trong {timeout}s")


@pytest.mark.asyncio
async def test_submit_runs_job_and_records_result(store):
    async def runner(progress):
        progress("WORKING", 50)
        return {"chunk_count": 3}

    record = store.submit("INGESTION", runner, job_id="job-1")
    assert record.state == "QUEUED"

    await _wait_for_terminal(store, "job-1")
    done = store.get("job-1")
    assert done.state == "COMPLETED"
    assert done.progress_percent == 100
    assert done.result == {"chunk_count": 3}
    assert done.error is None


@pytest.mark.asyncio
async def test_failed_runner_marks_job_failed_with_message(store):
    async def runner(progress):
        raise ValueError("chunk rỗng")

    store.submit("INGESTION", runner, job_id="job-2")
    await _wait_for_terminal(store, "job-2")

    done = store.get("job-2")
    assert done.state == "FAILED"
    assert "ValueError: chunk rỗng" in done.error


@pytest.mark.asyncio
async def test_duplicate_submit_rejected_while_job_not_terminal(store):
    started = asyncio.Event()
    release = asyncio.Event()

    async def runner(progress):
        started.set()
        await release.wait()
        return {}

    store.submit("EVALUATION", runner, job_id="job-3")
    await started.wait()

    with pytest.raises(JobExistsError):
        store.submit("EVALUATION", runner, job_id="job-3")

    release.set()
    await _wait_for_terminal(store, "job-3")

    # Job đã kết thúc thì Backend được phép submit lại cùng job_id (retry).
    store.submit("EVALUATION", lambda progress: _immediate(), job_id="job-3")
    await _wait_for_terminal(store, "job-3")
    assert store.get("job-3").state == "COMPLETED"


async def _immediate() -> dict:
    return {"ok": True}


@pytest.mark.asyncio
async def test_same_kind_jobs_do_not_run_concurrently(store):
    running = 0
    max_running = 0

    async def runner(progress):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.02)
        running -= 1
        return {}

    store.submit("INDEX_REBUILD", runner, job_id="idx-1")
    store.submit("INDEX_REBUILD", runner, job_id="idx-2")
    await _wait_for_terminal(store, "idx-1")
    await _wait_for_terminal(store, "idx-2")

    assert max_running == 1


def test_state_survives_new_store_instance(tmp_path):
    root = str(tmp_path / "jobs")
    JobStore(root).create("INGESTION", job_id="job-4")

    reopened = JobStore(root).get("job-4")
    assert reopened is not None
    assert reopened.state == "QUEUED"


def test_recover_stale_fails_unfinished_jobs(tmp_path):
    root = str(tmp_path / "jobs")
    store = JobStore(root)
    store.create("INGESTION", job_id="stale-1")
    store.create("EVALUATION", job_id="done-1")
    store._update("done-1", state="COMPLETED")  # noqa: SLF001 — dựng trạng thái kết thúc

    recovered = JobStore(root).recover_stale()

    assert recovered == ["stale-1"]
    assert store.get("stale-1").state == "FAILED"
    assert store.get("stale-1").error == RESTART_ERROR
    assert store.get("done-1").state == "COMPLETED"


def test_job_id_cannot_escape_jobs_directory(tmp_path):
    root = tmp_path / "jobs"
    store = JobStore(str(root))

    store.create("INGESTION", job_id="../../evil")

    assert store.get("../../evil") is not None
    assert [p.name for p in tmp_path.iterdir()] == ["jobs"]
    assert all(p.parent == root for p in root.iterdir())
