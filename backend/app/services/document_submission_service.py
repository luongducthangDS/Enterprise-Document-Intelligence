import base64
import hashlib
import io
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException, ConflictError, ForbiddenError, NotFoundError
from app.domain.models.audit import AuditLogDB
from app.domain.models.documents import DocumentDB, DocumentSubmissionDB
from app.services.access_control import DEPARTMENT_MANAGER, SUPER_ADMIN, normalized_role, same_department
from app.services.document_service import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    DocumentService,
    _resolve_document_department,
)
from app.services.worker_job_client import WorkerJobClient, WorkerJobClientError

REVIEWABLE_STATES = {"PENDING_REVIEW"}
ANALYSIS_ACTIVE_STATES = {"ANALYZING"}
PUBLICATION_ACTIVE_STATES = {"APPROVING", "PUBLISHING"}
TERMINAL_STATES = {
    "PENDING_REVIEW",
    "PUBLISHED",
    "ANALYSIS_FAILED",
    "PUBLISH_FAILED",
    "CHANGES_REQUESTED",
    "REJECTED",
}


class DocumentSubmissionService:
    worker_client = WorkerJobClient()
    worker_dispatch_enabled = True

    @staticmethod
    def _actor_id(user: dict[str, Any]) -> uuid.UUID:
        raw = user.get("user_id") or user.get("profile_id") or user.get("sub") or user.get("id")
        try:
            return uuid.UUID(str(raw))
        except (TypeError, ValueError) as exc:
            raise AppException(401, "IDENTITY_REQUIRED", "Không xác định được người thực hiện.") from exc

    @staticmethod
    def _can_manage(user: dict[str, Any], submission: DocumentSubmissionDB) -> bool:
        role = normalized_role(user)
        return role == SUPER_ADMIN or (
            role == DEPARTMENT_MANAGER and same_department(user, submission.department)
        )

    @classmethod
    async def _load(cls, db: AsyncSession, user: dict[str, Any], submission_id: str) -> DocumentSubmissionDB:
        try:
            value = uuid.UUID(submission_id)
        except ValueError as exc:
            raise NotFoundError("SUBMISSION_NOT_FOUND", "Không tìm thấy tài liệu chờ duyệt.") from exc
        submission = await db.get(DocumentSubmissionDB, value)
        if submission is None or submission.tenant != get_settings().active_tenant:
            raise NotFoundError("SUBMISSION_NOT_FOUND", "Không tìm thấy tài liệu chờ duyệt.")
        if not cls._can_manage(user, submission) and submission.submitted_by != cls._actor_id(user):
            raise ForbiddenError("Bạn không có quyền xem tài liệu chờ duyệt này.", "SUBMISSION_ACCESS_DENIED")
        return submission

    @staticmethod
    def _safe_error(error: Any) -> str | None:
        if not error:
            return None
        return "Không thể phân tích tài liệu. Hãy kiểm tra định dạng và nội dung file."

    @classmethod
    async def _sync(cls, db: AsyncSession, user: dict[str, Any], submission: DocumentSubmissionDB) -> None:
        if cls.worker_dispatch_enabled and submission.status in ANALYSIS_ACTIVE_STATES:
            try:
                worker = await cls.worker_client.get_status(str(submission.id))
            except WorkerJobClientError as exc:
                print(f"[SUBMISSION-SYNC-WARN] WorkerJobClientError for submission {submission.id}: {exc}")
                worker = None
            if worker:
                submission.stage = str(worker.get("stage", submission.stage))
                submission.progress_percent = int(worker.get("progress_percent", submission.progress_percent))
                print(f"[SUBMISSION-SYNC] submission_id={submission.id} worker_state={worker.get('state')} stage={submission.stage} progress={submission.progress_percent}%")
                if worker.get("state") == "COMPLETED":
                    result = worker.get("result") or {}
                    submission.status = "PENDING_REVIEW"
                    submission.stage = "PENDING_REVIEW"
                    submission.progress_percent = 100
                    submission.extract_method = str(result.get("extract_method") or "UNKNOWN")
                    submission.extracted_text = str(result.get("extracted_text") or "")
                    submission.chunks = list(result.get("chunks") or [])
                    submission.chunk_count = int(result.get("chunk_count") or len(submission.chunks))
                    submission.analysis_warnings = list(result.get("warnings") or [])
                    submission.error = None
                    print(f"[SUBMISSION-SYNC] 🟢 Submission {submission.id} is now PENDING_REVIEW ({submission.chunk_count} chunks)")
                elif worker.get("state") == "FAILED":
                    submission.status = "ANALYSIS_FAILED"
                    submission.stage = "FAILED"
                    submission.error = cls._safe_error(worker.get("error"))
                    print(f"[SUBMISSION-SYNC] 🔴 Submission {submission.id} ANALYSIS_FAILED: {submission.error}")
                await db.commit()

        if submission.status in PUBLICATION_ACTIVE_STATES and submission.publication_job_id:
            job = await DocumentService.get_ingestion_job(db, user, str(submission.publication_job_id))
            print(f"[SUBMISSION-PUBLISH-SYNC] submission_id={submission.id} pub_job_id={submission.publication_job_id} job_state={job.get('state')} stage={job.get('stage')}")
            if job["state"] == "COMPLETED":
                submission.status = "PUBLISHED"
                submission.stage = "PUBLISHED"
                submission.progress_percent = 100
                submission.error = None
                print(f"[SUBMISSION-PUBLISH-SYNC] 🟢 Submission {submission.id} PUBLISHED successfully!")
                await db.commit()
            elif job["state"] == "FAILED":
                submission.status = "PUBLISH_FAILED"
                submission.stage = "FAILED"
                submission.error = job.get("error") or "Không thể xuất bản tài liệu vào kho chính thức."
                print(f"[SUBMISSION-PUBLISH-SYNC] 🔴 Submission {submission.id} PUBLISH_FAILED: {submission.error}")
                await db.commit()

    @classmethod
    async def create_submission(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        file: UploadFile,
        *,
        title: str | None = None,
        category: str | None = None,
        department: str | None = None,
        version: str | None = None,
        effective_date: str | None = None,
        confidentiality: str | None = None,
        access_scope: str = "RESTRICTED",
        authorized_role: str | None = None,
        public_url: str | None = None,
    ) -> dict[str, Any]:
        actor_id = cls._actor_id(user)
        filename = os.path.basename((file.filename or "document.pdf").replace("\\", "/"))
        extension = os.path.splitext(filename)[1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise AppException(415, "UNSUPPORTED_FILE_TYPE", "Chỉ chấp nhận PDF, DOC, DOCX, MD, PNG, JPG hoặc WEBP.")

        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise AppException(413, "FILE_TOO_LARGE", "Dung lượng file vượt quá giới hạn 25MB.")
        if not contents.strip():
            raise AppException(422, "FILE_NOT_MACHINE_READABLE", "File rỗng hoặc không thể đọc.")

        normalized_category = category.strip() if category and category.strip() else "GENERAL"
        normalized_department = _resolve_document_department(department, normalized_category).upper()
        normalized_scope = access_scope.strip().upper()
        if normalized_scope not in {"COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"}:
            raise AppException(422, "INVALID_ACCESS_SCOPE", "Phạm vi truy cập không hợp lệ.")
        role_value = authorized_role.strip().upper() if authorized_role and authorized_role.strip() else None
        if normalized_scope == "ROLE" and not role_value:
            raise AppException(422, "AUTHORIZED_ROLE_REQUIRED", "Phạm vi ROLE yêu cầu vai trò được phép.")
        if normalized_scope != "ROLE":
            role_value = None

        role = normalized_role(user)
        if role == DEPARTMENT_MANAGER:
            if not same_department(user, normalized_department):
                raise ForbiddenError("Bạn chỉ được tải tài liệu của phòng ban mình.", "DEPARTMENT_SCOPE_DENIED")
            if normalized_scope not in {"DEPARTMENT", "RESTRICTED"}:
                raise ForbiddenError("Quản lý phòng ban không được mở tài liệu ra toàn công ty.", "SCOPE_MANAGEMENT_DENIED")
        elif role != SUPER_ADMIN:
            raise ForbiddenError("Bạn không có quyền tải tài liệu.", "FORBIDDEN")

        submission = DocumentSubmissionDB(
            tenant=get_settings().active_tenant,
            source_file=filename,
            content_type=file.content_type,
            file_content=contents,
            title=title.strip() if title and title.strip() else filename,
            category=normalized_category,
            department=normalized_department,
            version=version.strip() if version and version.strip() else None,
            effective_date=effective_date or None,
            confidentiality=confidentiality or "INTERNAL",
            access_scope=normalized_scope,
            authorized_role=role_value,
            public_url=public_url.strip() if public_url and public_url.strip() else None,
            submitted_by=actor_id,
            status="ANALYZING",
            stage="UPLOADED",
        )
        db.add(submission)
        await db.commit()
        await db.refresh(submission)

        if cls.worker_dispatch_enabled:
            try:
                await cls.worker_client.submit_document_analysis(
                    {
                        "job_id": str(submission.id),
                        "submission_id": str(submission.id),
                        "document_id": None,
                        "source_file": filename,
                        "content_base64": "" if submission.public_url else base64.b64encode(contents).decode("ascii"),
                        "content_url": submission.public_url or "",
                        "content_sha256": hashlib.sha256(contents).hexdigest(),
                        "category": submission.category,
                        "department": submission.department,
                        "tenant": submission.tenant,
                        "access_scope": submission.access_scope,
                        "authorized_role": submission.authorized_role or "",
                        "owner_user_id": str(actor_id),
                        "authorization_source": "RUNTIME_UPLOAD",
                        "publication_status": "draft",
                        "artifact_state": "draft",
                        "retrieval_enabled": False,
                        "expiry_date": "9999-12-31",
                        "source_type": "official_policy",
                        "is_official_policy": True,
                        "caveat": "",
                        "authority": "tenant_official_policy",
                        "provenance": "customer_provided",
                    }
                )
            except WorkerJobClientError:
                submission.status = "ANALYSIS_FAILED"
                submission.stage = "FAILED"
                submission.error = "Không thể khởi động quá trình phân tích tài liệu."
                await db.commit()

        return {
            "submission_id": str(submission.id),
            "analysis_job_id": str(submission.id),
            "status": submission.status,
            "stage": submission.stage,
            "poll_after_ms": 1000,
        }

    @classmethod
    async def list_submissions(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(DocumentSubmissionDB).where(
            DocumentSubmissionDB.tenant == get_settings().active_tenant
        ).order_by(desc(DocumentSubmissionDB.created_at))
        if normalized_role(user) == DEPARTMENT_MANAGER:
            stmt = stmt.where(DocumentSubmissionDB.department == str(user.get("department", "")).upper().strip())
        if status:
            stmt = stmt.where(DocumentSubmissionDB.status == status.upper())
        result = await db.execute(stmt)
        submissions = list(result.scalars().all())
        for submission in submissions:
            if submission.status in ANALYSIS_ACTIVE_STATES | PUBLICATION_ACTIVE_STATES:
                await cls._sync(db, user, submission)
        return [cls._summary(item) for item in submissions]

    @classmethod
    async def get_submission(
        cls, db: AsyncSession, user: dict[str, Any], submission_id: str
    ) -> dict[str, Any]:
        submission = await cls._load(db, user, submission_id)
        await cls._sync(db, user, submission)
        return cls._detail(submission)

    @classmethod
    async def approve(
        cls, db: AsyncSession, user: dict[str, Any], submission_id: str, note: str | None = None
    ) -> dict[str, Any]:
        submission = await cls._load(db, user, submission_id)
        if not cls._can_manage(user, submission):
            raise ForbiddenError("Bạn không có quyền duyệt tài liệu này.", "SUBMISSION_REVIEW_DENIED")
        if submission.status not in REVIEWABLE_STATES:
            raise ConflictError("SUBMISSION_NOT_REVIEWABLE", "Tài liệu chưa sẵn sàng hoặc đã được xử lý.")
        reviewer_id = cls._actor_id(user)
        submission.status = "APPROVING"
        submission.stage = "APPROVING"
        submission.reviewed_by = reviewer_id
        submission.reviewed_at = datetime.now(UTC)
        submission.review_note = note
        await db.commit()

        print(f"[SUBMISSION-APPROVE] Approving submission {submission.id} ({submission.title}) by user {reviewer_id}")
        try:
            upload = UploadFile(filename=submission.source_file, file=io.BytesIO(submission.file_content))
            published = await DocumentService.upload_document(
                db,
                user,
                upload,
                title=submission.title,
                category=submission.category,
                department=submission.department,
                version=submission.version,
                effective_date=submission.effective_date,
                confidentiality=submission.confidentiality,
                status="ACTIVE",
                staging_submission_id=str(submission.id),
                access_scope=submission.access_scope,
                authorized_role=submission.authorized_role,
                public_url=submission.public_url,
            )
            print(f"[SUBMISSION-APPROVE] Published document_id={published['document_id']}, ingestion_job_id={published['ingestion_job_id']}")
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            print(f"[SUBMISSION-APPROVE-ERROR] 🔴 Failed to publish document: {exc}\n{tb}")
            submission.status = "PUBLISH_FAILED"
            submission.stage = "FAILED"
            submission.error = f"Lỗi xuất bản: {exc}"
            await db.commit()
            raise

        submission.published_document_id = uuid.UUID(published["document_id"])
        submission.publication_job_id = uuid.UUID(published["ingestion_job_id"])
        submission.status = "PUBLISHING"
        submission.stage = "PUBLISHING"
        submission.progress_percent = 0
        db.add(
            AuditLogDB(
                tenant=submission.tenant,
                actor_id=reviewer_id,
                action="DOCUMENT_SUBMISSION_APPROVED",
                resource_type="document_submission",
                resource_id=str(submission.id),
                before_state={"status": "PENDING_REVIEW"},
                after_state={"status": "PUBLISHING", "document_id": published["document_id"]},
            )
        )
        await db.commit()
        return cls._detail(submission)

    @classmethod
    async def update_public_url(
        cls, db: AsyncSession, user: dict[str, Any], submission_id: str, public_url: str
    ) -> dict[str, Any]:
        submission = await cls._load(db, user, submission_id)
        actor_id = cls._actor_id(user)
        role = normalized_role(user)
        if submission.submitted_by != actor_id and role != SUPER_ADMIN and not (
            role == DEPARTMENT_MANAGER and same_department(user, submission.department)
        ):
            raise ForbiddenError("Bạn không có quyền cập nhật đường dẫn tài liệu này.", "FORBIDDEN")

        clean_url = public_url.strip() if public_url and public_url.strip() else None
        submission.public_url = clean_url
        if submission.published_document_id:
            doc = await db.get(DocumentDB, submission.published_document_id)
            if doc:
                doc.public_url = clean_url
        await db.commit()
        return cls._detail(submission)

    @classmethod
    async def reject(
        cls, db: AsyncSession, user: dict[str, Any], submission_id: str, note: str | None = None
    ) -> dict[str, Any]:
        submission = await cls._load(db, user, submission_id)
        if not cls._can_manage(user, submission):
            raise ForbiddenError("Bạn không có quyền từ chối tài liệu này.", "SUBMISSION_REVIEW_DENIED")
        await cls._sync(db, user, submission)
        if submission.status not in REVIEWABLE_STATES:
            raise ConflictError("SUBMISSION_NOT_REVIEWABLE", "Tài liệu chưa sẵn sàng hoặc đã được xử lý.")
        reviewer_id = cls._actor_id(user)
        submission.status = "REJECTED"
        submission.stage = "REJECTED"
        submission.reviewed_by = reviewer_id
        submission.reviewed_at = datetime.now(UTC)
        submission.review_note = note
        db.add(
            AuditLogDB(
                tenant=submission.tenant,
                actor_id=reviewer_id,
                action="DOCUMENT_SUBMISSION_REJECTED",
                resource_type="document_submission",
                resource_id=str(submission.id),
                before_state={"status": "PENDING_REVIEW"},
                after_state={"status": "REJECTED", "note": note},
            )
        )
        await db.commit()
        return cls._detail(submission)

    @staticmethod
    def _summary(item: DocumentSubmissionDB) -> dict[str, Any]:
        return {
            "submission_id": str(item.id),
            "title": item.title,
            "source_file": item.source_file,
            "category": item.category,
            "department": item.department,
            "version": item.version,
            "status": item.status,
            "public_url": item.public_url,
            "stage": item.stage,
            "progress_percent": item.progress_percent,
            "extract_method": item.extract_method,
            "chunk_count": item.chunk_count,
            "submitted_by": str(item.submitted_by),
            "created_at": item.created_at.isoformat(),
            "published_document_id": str(item.published_document_id) if item.published_document_id else None,
            "error": item.error,
        }

    @classmethod
    def _detail(cls, item: DocumentSubmissionDB) -> dict[str, Any]:
        return {
            **cls._summary(item),
            "metadata": {
                "title": item.title,
                "source_file": item.source_file,
                "category": item.category,
                "department": item.department,
                "version": item.version,
                "effective_date": item.effective_date,
                "confidentiality": item.confidentiality,
                "access_scope": item.access_scope,
                "authorized_role": item.authorized_role,
            },
            "analysis": {
                "extract_method": item.extract_method,
                "extracted_text": item.extracted_text or "",
                "character_count": len(item.extracted_text or ""),
                "chunk_count": item.chunk_count,
                "chunks": item.chunks or [],
                "warnings": item.analysis_warnings or [],
            },
            "review": {
                "reviewed_by": str(item.reviewed_by) if item.reviewed_by else None,
                "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                "note": item.review_note,
            },
            "poll_after_ms": 1000,
        }
