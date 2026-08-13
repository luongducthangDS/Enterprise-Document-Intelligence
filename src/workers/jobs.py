"""Job runner cho các tác vụ dài phía Agent (ingestion / index rebuild / evaluation).

Ranh giới với Backend (xem docs/rag-pipeline/AGENT_WORKERS.md):
- Backend sở hữu bảng job, lifecycle nghiệp vụ, retry policy, API cho FE.
- Agent chỉ sở hữu EXECUTION: nhận job, chạy pipeline AI, báo trạng thái.

Vì sao ghi ra đĩa thay vì giữ trong RAM: bug report 13/08 (finding #3) chỉ ra
đúng loại lỗi khi trạng thái job chỉ nằm trong bộ nhớ tiến trình — process
restart là job kẹt vĩnh viễn ở QUEUED. Ở đây mọi lần đổi trạng thái đều ghi
atomically xuống `agent_jobs_dir`, và `recover_stale()` lúc startup đẩy các job
còn dở sang FAILED để Backend poll ra trạng thái kết thúc (rồi tự quyết retry)
thay vì chờ mãi. Agent KHÔNG tự chạy lại job — retry là quyết định của Backend,
nơi có bản ghi job thật.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

JobKind = Literal["INGESTION", "INDEX_REBUILD", "EVALUATION"]
JobState = Literal["QUEUED", "PROCESSING", "COMPLETED", "FAILED"]

TERMINAL_STATES: frozenset[str] = frozenset({"COMPLETED", "FAILED"})

# Lỗi ghi vào job khi agent restart giữa chừng — Backend nhìn thấy chuỗi này thì
# biết job chưa từng chạy xong và có thể submit lại an toàn.
RESTART_ERROR = "AGENT_RESTARTED: job bị bỏ dở do agent khởi động lại, cần submit lại"

MAX_ERROR_CHARS = 2000


class JobExistsError(Exception):
    """job_id đã tồn tại và chưa kết thúc — chặn double-submit từ Backend."""


class JobRecord(BaseModel):
    job_id: str
    kind: JobKind
    state: JobState = "QUEUED"
    stage: str = "QUEUED"
    progress_percent: int = Field(default=0, ge=0, le=100)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


# Hàm chạy thật của 1 job: nhận callback báo tiến độ, trả dict kết quả.
ProgressCallback = Callable[[str, int], None]
JobRunner = Callable[[ProgressCallback], Awaitable[dict[str, Any]]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    """Lưu trạng thái job ra file JSON (1 file/job) + chạy job bằng asyncio task."""

    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)
        self._tasks: dict[str, asyncio.Task] = {}
        # Index rebuild và evaluation đều đụng vào cùng collection Chroma /
        # cùng hạn mức API embedding, chạy song song chỉ làm chậm và dễ đá nhau.
        self._kind_locks: dict[str, asyncio.Lock] = {}

    # --- persistence -----------------------------------------------------

    def _path(self, job_id: str) -> str:
        # job_id đến từ Backend -> không cho phép thoát khỏi thư mục job.
        safe = job_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return os.path.join(self.root, f"{safe}.json")

    def _write(self, record: JobRecord) -> None:
        path = self._path(record.job_id)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(record.model_dump(), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def get(self, job_id: str) -> JobRecord | None:
        path = self._path(job_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return JobRecord(**json.load(f))
        except (OSError, ValueError) as exc:  # file hỏng/ghi dở -> coi như không có
            logger.warning("Không đọc được job %s: %s", job_id, exc)
            return None

    def list_jobs(self) -> list[JobRecord]:
        records = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json"):
                continue
            record = self.get(name[: -len(".json")])
            if record:
                records.append(record)
        return records

    def _update(self, job_id: str, **fields: Any) -> JobRecord | None:
        record = self.get(job_id)
        if record is None:
            return None
        updated = record.model_copy(update={**fields, "updated_at": _now()})
        self._write(updated)
        return updated

    # --- lifecycle -------------------------------------------------------

    def create(self, kind: JobKind, job_id: str | None = None) -> JobRecord:
        job_id = job_id or str(uuid.uuid4())
        existing = self.get(job_id)
        if existing and existing.state not in TERMINAL_STATES:
            raise JobExistsError(f"Job {job_id} đang ở trạng thái {existing.state}")

        record = JobRecord(job_id=job_id, kind=kind, created_at=_now(), updated_at=_now())
        self._write(record)
        return record

    def submit(self, kind: JobKind, runner: JobRunner, job_id: str | None = None) -> JobRecord:
        """Tạo job rồi chạy nền. Trả về record ở trạng thái QUEUED."""
        record = self.create(kind, job_id)
        task = asyncio.create_task(self._run(record.job_id, kind, runner))
        self._tasks[record.job_id] = task
        task.add_done_callback(lambda _t, jid=record.job_id: self._tasks.pop(jid, None))
        return record

    async def _run(self, job_id: str, kind: JobKind, runner: JobRunner) -> None:
        lock = self._kind_locks.setdefault(kind, asyncio.Lock())
        # Giữ nguyên QUEUED trong lúc chờ lock — Backend poll ra "đang xếp hàng"
        # đúng như thực tế, thay vì PROCESSING giả.
        async with lock:
            self._update(job_id, state="PROCESSING", stage="STARTED", progress_percent=1)

            def progress(stage: str, percent: int) -> None:
                self._update(job_id, stage=stage, progress_percent=max(0, min(100, int(percent))))

            try:
                result = await runner(progress)
            except asyncio.CancelledError:
                self._update(job_id, state="FAILED", stage="CANCELLED", error="Job bị huỷ")
                raise
            except Exception as exc:  # noqa: BLE001 — lỗi 1 job không được giết agent
                logger.exception("Job %s (%s) thất bại", job_id, kind)
                self._update(
                    job_id,
                    state="FAILED",
                    stage="FAILED",
                    error=f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS],
                )
                return

            self._update(
                job_id,
                state="COMPLETED",
                stage="COMPLETED",
                progress_percent=100,
                result=result,
                error=None,
            )

    def recover_stale(self) -> list[str]:
        """Đánh dấu FAILED mọi job còn QUEUED/PROCESSING trên đĩa (gọi lúc startup)."""
        recovered = []
        for record in self.list_jobs():
            if record.state in TERMINAL_STATES:
                continue
            self._update(record.job_id, state="FAILED", stage="FAILED", error=RESTART_ERROR)
            recovered.append(record.job_id)
        if recovered:
            logger.warning("Đã đánh dấu FAILED %d job dang dở sau khi agent restart", len(recovered))
        return recovered


_store: JobStore | None = None


def get_job_store(settings: Settings | None = None) -> JobStore:
    global _store
    if _store is None:
        _store = JobStore((settings or get_settings()).agent_jobs_dir)
    return _store


def reset_job_store() -> None:
    """Chỉ dùng trong test — bỏ instance đang cache để đổi thư mục job."""
    global _store
    _store = None
