import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ConflictError, ForbiddenError, NotFoundError
from app.domain.models.documents import DocumentDB, IngestionJobDB
from app.schemas.documents import DocumentMetadataUpdate
from app.services.worker_job_client import WorkerJobClient, WorkerJobClientError

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".md"}


class DocumentService:
    worker_client = WorkerJobClient()
    worker_dispatch_enabled = True

    @classmethod
    async def upload_document(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        file: UploadFile,
        title: str | None = None,
        category: str | None = None,
        version: str | None = None,
        effective_date: str | None = None,
        confidentiality: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        uploader_id_raw = user.get("user_id") or user.get("profile_id") or user.get("sub") or user.get("id")
        try:
            uploader_id = uuid.UUID(str(uploader_id_raw))
        except (ValueError, TypeError):
            uploader_id = uuid.uuid4()


        filename = file.filename or "document.pdf"
        ext = os.path.splitext(filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise AppException(
                status_code=415,
                code="UNSUPPORTED_FILE_TYPE",
                message="Định dạng file không được hỗ trợ. Chỉ chấp nhận PDF, DOC, DOCX, MD.",
            )

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise AppException(
                status_code=413,
                code="FILE_TOO_LARGE",
                message="Dung lượng file vượt quá giới hạn 25MB.",
            )

        if len(contents.strip()) == 0:
            raise AppException(
                status_code=422,
                code="FILE_NOT_MACHINE_READABLE",
                message="Nội dung file rỗng hoặc không thể trích xuất văn bản.",
            )

        doc_title = title.strip() if title and title.strip() else filename
        doc_category = category.strip() if category and category.strip() else "GENERAL"
        doc_confidentiality = confidentiality.strip() if confidentiality and confidentiality.strip() else "INTERNAL"
        doc_status = status.strip() if status and status.strip() else "ACTIVE"

        doc = DocumentDB(
            title=doc_title,
            source_file=filename,
            category=doc_category,
            version=version,
            effective_date=effective_date,
            confidentiality=doc_confidentiality,
            status=doc_status,
            uploaded_by=uploader_id,
        )
        db.add(doc)
        await db.flush()

        job = IngestionJobDB(
            document_id=doc.id,
            state="QUEUED",
            stage="UPLOADED",
            progress_percent=0,
        )
        db.add(job)
        await db.commit()
        await db.refresh(doc)
        await db.refresh(job)

        if cls.worker_dispatch_enabled:
            try:
                await cls.worker_client.submit_ingestion(
                    {
                        "job_id": str(job.id),
                        "document_id": str(doc.id),
                        "source_file": filename,
                        "content_base64": base64.b64encode(contents).decode("ascii"),
                        "category": doc.category,
                        "source_type": "official_policy",
                        "is_official_policy": True,
                        "caveat": doc.caveat or "",
                        "authority": "tenant_official_policy",
                        "provenance": "customer_provided",
                    }
                )
            except WorkerJobClientError as exc:
                job.state = "FAILED"
                job.stage = "FAILED"
                job.error = str(exc)
                await db.commit()

        return {
            "document_id": str(doc.id),
            "ingestion_job_id": str(job.id),
            "status": doc.status,
        }

    @classmethod
    async def list_documents(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        status: str | None = None,
        category: str | None = None,
        ingestion_state: str | None = None,
        indexed: bool | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        stmt = select(DocumentDB).order_by(desc(DocumentDB.created_at))

        if status:
            stmt = stmt.where(DocumentDB.status == status)
        if category:
            stmt = stmt.where(DocumentDB.category == category)

        res = await db.execute(stmt)
        docs = res.scalars().all()

        formatted_list = []
        for doc in docs:
            job_stmt = (
                select(IngestionJobDB)
                .where(IngestionJobDB.document_id == doc.id)
                .order_by(desc(IngestionJobDB.created_at))
            )
            job_res = await db.execute(job_stmt)
            job = job_res.scalars().first()

            current_ingestion_state = job.state if job else "QUEUED"
            is_indexed = doc.chroma_indexed_at is not None

            if ingestion_state and current_ingestion_state != ingestion_state:
                continue
            if indexed is not None and is_indexed != indexed:
                continue

            formatted_list.append(
                {
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "category": doc.category,
                    "version": doc.version,
                    "effective_date": doc.effective_date,
                    "status": doc.status,
                    "ingestion_state": current_ingestion_state,
                    "indexed": is_indexed,
                    "created_at": doc.created_at.isoformat(),
                }
            )

        limit_val = min(max(1, limit), 100)
        sliced = formatted_list[:limit_val]
        next_cursor = sliced[-1]["document_id"] if len(formatted_list) > limit_val else None

        pagination = {
            "limit": limit_val,
            "next_cursor": next_cursor,
        }

        return sliced, pagination

    @classmethod
    async def get_document_detail(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        document_id: str,
    ) -> dict[str, Any]:
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise NotFoundError(code="DOCUMENT_NOT_FOUND", message="Không tìm thấy tài liệu.")

        stmt = select(DocumentDB).where(DocumentDB.id == doc_uuid)
        res = await db.execute(stmt)
        doc = res.scalars().first()

        if not doc:
            raise NotFoundError(code="DOCUMENT_NOT_FOUND", message="Không tìm thấy tài liệu.")

        # User role confidentiality check
        user_role = user.get("role", "EMPLOYEE")
        if doc.confidentiality in ("RESTRICTED", "CONFIDENTIAL") and user_role not in (
            "HR_ADMIN",
            "SUPER_ADMIN",
        ):
            raise ForbiddenError(code="DOCUMENT_ACCESS_DENIED", message="Bạn không có quyền truy cập tài liệu này.")

        job_stmt = (
            select(IngestionJobDB)
            .where(IngestionJobDB.document_id == doc.id)
            .order_by(desc(IngestionJobDB.created_at))
        )
        job_res = await db.execute(job_stmt)
        job = job_res.scalars().first()

        job_id = str(job.id) if job else None
        job_state = job.state if job else "QUEUED"
        chunk_count = job.chunk_count if job else 0
        last_ingested_at = job.updated_at.isoformat() if (job and job.state == "COMPLETED") else None
        job_error = job.error if job else None

        is_indexed = doc.chroma_indexed_at is not None
        index_version = "v1.0" if is_indexed else None
        checksum = hashlib.sha256(doc.source_file.encode()).hexdigest()[:16]

        return {
            "document_id": str(doc.id),
            "title": doc.title,
            "category": doc.category,
            "version": doc.version,
            "effective_date": doc.effective_date,
            "status": doc.status,
            "language": "vi",
            "source_file": doc.source_file,
            "checksum": checksum,
            "confidentiality": doc.confidentiality,
            "ingestion": {
                "job_id": job_id,
                "state": job_state,
                "chunk_count": chunk_count,
                "last_ingested_at": last_ingested_at,
                "error": job_error,
            },
            "index": {
                "indexed": is_indexed,
                "index_version": index_version,
            },
        }

    @classmethod
    async def update_document_metadata(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        document_id: str,
        data: DocumentMetadataUpdate,
    ) -> dict[str, Any]:
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise NotFoundError(code="DOCUMENT_NOT_FOUND", message="Không tìm thấy tài liệu.")

        stmt = select(DocumentDB).where(DocumentDB.id == doc_uuid)
        res = await db.execute(stmt)
        doc = res.scalars().first()

        if not doc:
            raise NotFoundError(code="DOCUMENT_NOT_FOUND", message="Không tìm thấy tài liệu.")

        user_role = user.get("role", "EMPLOYEE")
        if user_role not in ("HR_ADMIN", "SUPER_ADMIN"):
            raise ForbiddenError(
                code="FORBIDDEN",
                message="Bạn không có quyền cập nhật metadata cho tài liệu này.",
            )

        if data.title is not None:
            doc.title = data.title
        if data.category is not None:
            doc.category = data.category
        if data.version is not None:
            doc.version = data.version
        if data.effective_date is not None:
            doc.effective_date = data.effective_date
        if data.status is not None:
            doc.status = data.status
        if data.confidentiality is not None:
            doc.confidentiality = data.confidentiality

        doc.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(doc)

        return {
            "document_id": str(doc.id),
            "metadata_updated": True,
            "requires_reindex": True,
            "updated_at": doc.updated_at.isoformat(),
        }

    @classmethod
    async def archive_document(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        document_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise NotFoundError(code="DOCUMENT_NOT_FOUND", message="Không tìm thấy tài liệu.")

        stmt = select(DocumentDB).where(DocumentDB.id == doc_uuid)
        res = await db.execute(stmt)
        doc = res.scalars().first()

        if not doc:
            raise NotFoundError(code="DOCUMENT_NOT_FOUND", message="Không tìm thấy tài liệu.")

        user_role = user.get("role", "EMPLOYEE")
        if user_role not in ("HR_ADMIN", "SUPER_ADMIN"):
            raise ForbiddenError(code="FORBIDDEN", message="Bạn không có quyền thao tác lưu trữ tài liệu.")

        if doc.status == "ARCHIVED":
            raise ConflictError(
                code="DOCUMENT_STATUS_CONFLICT",
                message="Tài liệu đã ở trạng thái ARCHIVED trước đó.",
            )

        doc.status = "ARCHIVED"
        if reason:
            doc.caveat = reason
        doc.updated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(doc)

        return {
            "document_id": str(doc.id),
            "status": "ARCHIVED",
            "requires_reindex": True,
            "archived_at": doc.updated_at.isoformat(),
        }

    @classmethod
    async def get_ingestion_job(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        job_id: str,
    ) -> dict[str, Any]:
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError:
            raise NotFoundError(code="INGESTION_JOB_NOT_FOUND", message="Không tìm thấy tác vụ ingestion.")

        stmt = select(IngestionJobDB).where(IngestionJobDB.id == job_uuid)
        res = await db.execute(stmt)
        job = res.scalars().first()

        if not job:
            raise NotFoundError(code="INGESTION_JOB_NOT_FOUND", message="Không tìm thấy tác vụ ingestion.")

        if cls.worker_dispatch_enabled and job.state not in ("COMPLETED", "FAILED"):
            try:
                worker = await cls.worker_client.get_status(str(job.id))
            except WorkerJobClientError:
                worker = None
            if worker:
                job.state = str(worker.get("state", job.state))
                job.stage = str(worker.get("stage", job.stage))
                job.progress_percent = int(worker.get("progress_percent", job.progress_percent))
                job.error = worker.get("error")
                result = worker.get("result") or {}
                if job.state == "COMPLETED":
                    job.chunk_count = int(result.get("chunk_count", 0))
                    document = await db.get(DocumentDB, job.document_id)
                    if document:
                        document.processed_path = result.get("processed_path")
                        document.chunks_path = result.get("chunks_path")
                        document.chroma_indexed_at = datetime.now(UTC)
                await db.commit()

        return {
            "job_id": str(job.id),
            "document_id": str(job.document_id),
            "state": job.state,
            "stage": job.stage,
            "progress_percent": job.progress_percent,
            "error": job.error,
            "poll_after_ms": 1000,
        }
