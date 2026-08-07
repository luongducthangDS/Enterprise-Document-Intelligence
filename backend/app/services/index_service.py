import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ConflictError, NotFoundError
from app.domain.models.documents import DocumentDB
from app.domain.models.index_job import IndexJobDB
from app.schemas.indexes import IndexRebuildRequest


class IndexService:
    @classmethod
    async def create_rebuild_job(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        request_data: IndexRebuildRequest,
    ) -> dict[str, Any]:
        requested_by_raw = user.get("user_id") or user.get("profile_id") or user.get("sub") or user.get("id")
        try:
            requested_by = uuid.UUID(str(requested_by_raw))
        except (ValueError, TypeError):
            requested_by = uuid.uuid4()

        # Check if another rebuild job is currently active (QUEUED or PROCESSING)
        active_stmt = select(IndexJobDB).where(IndexJobDB.state.in_(["QUEUED", "PROCESSING"]))
        active_res = await db.execute(active_stmt)
        active_job = active_res.scalars().first()

        if active_job:
            raise ConflictError(
                code="INDEX_REBUILD_IN_PROGRESS",
                message="Đang có tác vụ tái lập chỉ mục đang thực thi. Vui lòng chờ hoàn tất.",
            )

        # Validate specified document readiness
        if request_data.document_ids:
            for doc_id_str in request_data.document_ids:
                try:
                    doc_uuid = uuid.UUID(doc_id_str)
                except ValueError:
                    raise AppException(
                        status_code=422,
                        code="DOCUMENT_NOT_READY",
                        message=f"Tài liệu ID '{doc_id_str}' không hợp lệ hoặc chưa sẵn sàng.",
                    )

                doc_stmt = select(DocumentDB).where(DocumentDB.id == doc_uuid)
                doc_res = await db.execute(doc_stmt)
                doc = doc_res.scalars().first()

                if not doc or doc.status == "ARCHIVED":
                    raise AppException(
                        status_code=422,
                        code="DOCUMENT_NOT_READY",
                        message=f"Tài liệu '{doc_id_str}' không tồn tại hoặc ở trạng thái không thể index.",
                    )

        job = IndexJobDB(
            requested_by=requested_by,
            document_ids=request_data.document_ids,
            strategy=request_data.strategy or "REPLACE",
            state="QUEUED",
            stage="QUEUED",
            progress_percent=0,
            active_index_version="v1.0",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        return {
            "job_id": str(job.id),
            "state": job.state,
            "poll_after_ms": 2000,
        }

    @classmethod
    async def get_rebuild_job_status(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        job_id: str,
    ) -> dict[str, Any]:
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError:
            raise NotFoundError(
                code="INDEX_JOB_NOT_FOUND",
                message="Không tìm thấy thông tin tác vụ tái lập chỉ mục.",
            )

        stmt = select(IndexJobDB).where(IndexJobDB.id == job_uuid)
        res = await db.execute(stmt)
        job = res.scalars().first()

        if not job:
            raise NotFoundError(
                code="INDEX_JOB_NOT_FOUND",
                message="Không tìm thấy thông tin tác vụ tái lập chỉ mục.",
            )

        return {
            "job_id": str(job.id),
            "state": job.state,
            "stage": job.stage,
            "progress_percent": job.progress_percent,
            "active_index_version": job.active_index_version,
            "error": job.error,
            "poll_after_ms": 2000,
        }
