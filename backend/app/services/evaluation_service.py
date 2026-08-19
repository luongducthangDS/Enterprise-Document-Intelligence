import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.models.evaluation import EvaluationRunDB
from app.schemas.evaluation import EvaluationRunRequest
from app.services.worker_job_client import WorkerJobClient, WorkerJobClientError

VALID_DATASETS = {"evalset_hr_v1", "evalset_hr_v2", "evalset_default"}


class EvaluationService:
    worker_client = WorkerJobClient()
    worker_dispatch_enabled = True

    @classmethod
    async def create_evaluation_run(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        request_data: EvaluationRunRequest,
    ) -> dict[str, Any]:
        dataset_id = request_data.dataset_id.strip() if request_data.dataset_id else ""
        if not dataset_id or (
            dataset_id.startswith("invalid_") or dataset_id not in VALID_DATASETS and "evalset" not in dataset_id
        ):
            raise NotFoundError(
                code="EVALUATION_DATASET_NOT_FOUND",
                message="Không tìm thấy bộ dữ liệu đánh giá chỉ định.",
            )

        requested_by_raw = user.get("user_id") or user.get("profile_id") or user.get("sub") or user.get("id")
        try:
            requested_by = uuid.UUID(str(requested_by_raw))
        except (ValueError, TypeError):
            requested_by = uuid.uuid4()

        # Check if an evaluation run is currently active (QUEUED or PROCESSING)
        active_stmt = select(EvaluationRunDB).where(EvaluationRunDB.state.in_(["QUEUED", "PROCESSING"]))
        active_res = await db.execute(active_stmt)
        active_run = active_res.scalars().first()

        if active_run:
            raise ConflictError(
                code="EVALUATION_RUN_CONFLICT",
                message="Đang có đợt đánh giá chất lượng RAG đang thực thi. Vui lòng chờ hoàn tất.",
            )

        run = EvaluationRunDB(
            dataset_id=dataset_id,
            index_version=request_data.index_version or "v1.0",
            model_config_id=request_data.model_config_id or "default",
            requested_by=requested_by,
            state="QUEUED",
            stage="QUEUED",
            progress_percent=0,
            quality_gate="PENDING",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        if cls.worker_dispatch_enabled:
            try:
                await cls.worker_client.submit_evaluation(
                    {
                        "job_id": str(run.id),
                        "dataset_id": run.dataset_id,
                    }
                )
            except WorkerJobClientError as exc:
                run.state = "FAILED"
                run.stage = "FAILED"
                run.error = str(exc)
                await db.commit()

        return {
            "run_id": str(run.id),
            "state": run.state,
            "poll_after_ms": 3000,
        }

    @classmethod
    async def get_evaluation_run_status(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        run_id: str,
    ) -> dict[str, Any]:
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            raise NotFoundError(
                code="EVALUATION_RUN_NOT_FOUND",
                message="Không tìm thấy thông tin lượt đánh giá.",
            )

        stmt = select(EvaluationRunDB).where(EvaluationRunDB.id == run_uuid)
        res = await db.execute(stmt)
        run = res.scalars().first()

        if not run:
            raise NotFoundError(
                code="EVALUATION_RUN_NOT_FOUND",
                message="Không tìm thấy thông tin lượt đánh giá.",
            )

        if cls.worker_dispatch_enabled and run.state not in ("COMPLETED", "FAILED"):
            try:
                worker = await cls.worker_client.get_status(str(run.id))
            except WorkerJobClientError:
                worker = None
            if worker:
                run.state = str(worker.get("state", run.state))
                run.stage = str(worker.get("stage", run.stage))
                run.progress_percent = int(worker.get("progress_percent", run.progress_percent))
                run.error = worker.get("error")
                result = worker.get("result") or {}
                if run.state == "COMPLETED":
                    metrics = dict(result.get("metrics") or {})
                    if "recall_at_k" in metrics:
                        metrics["recall_at_5"] = metrics["recall_at_k"]
                    run.metrics = metrics
                    run.quality_gate = str(result.get("quality_gate") or "PENDING")
                await db.commit()

        return {
            "run_id": str(run.id),
            "dataset_id": run.dataset_id,
            "state": run.state,
            "stage": run.stage,
            "progress_percent": run.progress_percent,
            "metrics": run.metrics,
            "quality_gate": run.quality_gate,
            "error": run.error,
            "poll_after_ms": 3000,
        }
