import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import UploadFile
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException, ConflictError, ForbiddenError, NotFoundError
from app.domain.models.audit import AuditLogDB
from app.domain.models.documents import DocumentDB, IngestionJobDB
from app.schemas.documents import DocumentMetadataUpdate
from app.services.access_control import (
    DEPARTMENT_MANAGER,
    SUPER_ADMIN,
    can_manage_document,
    can_read_document,
    normalized_role,
    same_department,
)
from app.services.worker_job_client import WorkerJobClient, WorkerJobClientError

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".md", ".png", ".jpg", ".jpeg", ".webp"}

_PRODUCT_CATEGORIES = {"PRD", "ROADMAP", "USER_RESEARCH", "PRODUCT_METRICS"}
_ACCOUNTING_CATEGORIES = {
    "ADVANCE_AND_PAYMENT_SOP",
    "FIXED_ASSETS_MANAGEMENT",
    "INTERNAL_EXPENSE_POLICY",
    "INVOICES_AND_TAX",
    "PAYROLL_AND_COMPENSATION",
    "PROCUREMENT_AND_PURCHASING",
}


def _resolve_document_department(department: str | None, category: str) -> str:
    if department and department.strip():
        return department.strip()
    normalized_category = category.strip().upper()
    if normalized_category in _PRODUCT_CATEGORIES:
        return "Product"
    if normalized_category in _ACCOUNTING_CATEGORIES:
        return "ACCOUNTING"
    return "HR"


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
        department: str | None = None,
        version: str | None = None,
        effective_date: str | None = None,
        confidentiality: str | None = None,
        status: str | None = None,
        access_scope: str = "RESTRICTED",
        authorized_role: str | None = None,
        staging_submission_id: str | None = None,
        public_url: str | None = None,
    ) -> dict[str, Any]:
        uploader_id_raw = user.get("user_id") or user.get("profile_id") or user.get("sub") or user.get("id")
        try:
            uploader_id = uuid.UUID(str(uploader_id_raw))
        except (ValueError, TypeError) as exc:
            raise AppException(
                status_code=401, code="IDENTITY_REQUIRED", message="Không xác định được người tải tài liệu."
            ) from exc

        filename = file.filename or "document.pdf"
        ext = os.path.splitext(filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise AppException(
                status_code=415,
                code="UNSUPPORTED_FILE_TYPE",
                message="Định dạng file không được hỗ trợ. Chỉ chấp nhận PDF, DOC, DOCX, MD, PNG, JPG hoặc WEBP.",
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
        doc_department = _resolve_document_department(department, doc_category)
        doc_confidentiality = confidentiality.strip() if confidentiality and confidentiality.strip() else "INTERNAL"
        doc_status = status.strip().upper() if status and status.strip() else "ACTIVE"
        normalized_scope = access_scope.strip().upper()
        allowed_scopes = {"COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"}
        if normalized_scope not in allowed_scopes:
            raise AppException(status_code=422, code="INVALID_ACCESS_SCOPE", message="access_scope không hợp lệ.")
        normalized_authorized_role = authorized_role.strip().upper() if authorized_role and authorized_role.strip() else None
        if normalized_scope == "ROLE" and not normalized_authorized_role:
            raise AppException(
                status_code=422, code="AUTHORIZED_ROLE_REQUIRED", message="ROLE yêu cầu authorized_role."
            )
        if normalized_scope != "ROLE":
            normalized_authorized_role = None
        role = normalized_role(user)
        if role == DEPARTMENT_MANAGER:
            if not same_department(user, doc_department):
                raise ForbiddenError(code="DEPARTMENT_SCOPE_DENIED", message="Bạn chỉ được quản lý tài liệu của phòng ban mình.")
            if normalized_scope not in {"DEPARTMENT", "RESTRICTED"}:
                raise ForbiddenError(code="SCOPE_MANAGEMENT_DENIED", message="Quản lý phòng ban chỉ được tạo tài liệu nội bộ của phòng mình.")
        elif role != SUPER_ADMIN:
            raise ForbiddenError(code="FORBIDDEN", message="Bạn không có quyền tải tài liệu.")

        tenant = get_settings().active_tenant

        stmt = select(DocumentDB).where(DocumentDB.tenant == tenant, DocumentDB.source_file == filename)
        res = await db.execute(stmt)
        existing_doc = res.scalars().first()

        if existing_doc:
            if staging_submission_id:
                doc = existing_doc
                doc.title = doc_title
                doc.content_type = file.content_type
                doc.file_content = contents
                doc.category = doc_category
                doc.department = doc_department.upper()
                doc.access_scope = normalized_scope
                doc.authorized_role = normalized_authorized_role
                doc.version = version
                doc.effective_date = effective_date
                doc.confidentiality = doc_confidentiality
                doc.status = doc_status
                if public_url and public_url.strip():
                    doc.public_url = public_url.strip()
                doc.updated_at = datetime.now(UTC)
            else:
                raise ConflictError(
                    code="DOCUMENT_ALREADY_EXISTS",
                    message=(
                        f"Tài liệu '{filename}' đã tồn tại trong tenant '{tenant}'. "
                        "Dùng tên file khác hoặc xử lý thay thế/version ở tầng lifecycle."
                    ),
                )
        else:
            doc = DocumentDB(
                title=doc_title,
                source_file=filename,
                content_type=file.content_type,
                file_content=contents,
                category=doc_category,
                tenant=tenant,
                department=doc_department.upper(),
                access_scope=normalized_scope,
                authorized_role=normalized_authorized_role,
                owner_user_id=uploader_id,
                authorization_source="RUNTIME_UPLOAD",
                authority="tenant_official_policy",
                provenance="customer_provided",
                version=version,
                effective_date=effective_date,
                confidentiality=doc_confidentiality,
                status=doc_status,
                public_url=public_url.strip() if public_url and public_url.strip() else None,
                uploaded_by=uploader_id,
            )
            db.add(doc)
            try:
                await db.flush()
            except IntegrityError as exc:
                await db.rollback()
                raise ConflictError(
                    code="DOCUMENT_ALREADY_EXISTS",
                    message=(
                        f"Tài liệu '{filename}' đã tồn tại trong tenant '{tenant}'. "
                        "Dùng tên file khác hoặc xử lý thay thế/version ở tầng lifecycle."
                    ),
                ) from exc

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
                        "content_base64": "" if doc.public_url else base64.b64encode(contents).decode("ascii"),
                        "content_url": doc.public_url or "",
                        "content_sha256": hashlib.sha256(contents).hexdigest(),
                        "category": doc.category,
                        "department": doc_department,
                        "tenant": doc.tenant,
                        "access_scope": doc.access_scope,
                        "authorized_role": doc.authorized_role or "",
                        "owner_user_id": str(doc.owner_user_id),
                        "authorization_source": doc.authorization_source,
                        "publication_status": "active" if doc.status == "ACTIVE" else "draft",
                        "artifact_state": "frozen" if doc.status == "ACTIVE" else "draft",
                        "retrieval_enabled": doc.status == "ACTIVE",
                        "expiry_date": "9999-12-31",
                        "source_type": "official_policy",
                        "is_official_policy": True,
                        "caveat": doc.caveat or "",
                        "authority": "tenant_official_policy",
                        "provenance": "customer_provided",
                        "staging_source_stem": f"{staging_submission_id}__{os.path.splitext(filename)[0]}" if staging_submission_id else "",
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
            "access_scope": doc.access_scope,
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
        if normalized_role(user) == DEPARTMENT_MANAGER:
            stmt = stmt.where(DocumentDB.department == str(user.get("department", "")).upper().strip())

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
                    "public_url": doc.public_url,
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

        user_role = normalized_role(user)
        if not can_read_document(user, doc) or (
            doc.confidentiality in ("RESTRICTED", "CONFIDENTIAL") and user_role != SUPER_ADMIN
        ):
            raise ForbiddenError(code="DOCUMENT_ACCESS_DENIED", message="Bạn không có quyền truy cập tài liệu này.")

        job_stmt = (
            select(IngestionJobDB).where(IngestionJobDB.document_id == doc.id).order_by(desc(IngestionJobDB.created_at))
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
            "public_url": doc.public_url,
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
    async def update_public_url(
        cls,
        db: AsyncSession,
        user: dict[str, Any],
        document_id: str,
        public_url: str,
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

        if not can_manage_document(user, doc):
            raise ForbiddenError(code="FORBIDDEN", message="Bạn không có quyền cập nhật tài liệu này.")

        doc.public_url = public_url.strip() if public_url and public_url.strip() else None
        await db.commit()
        return await cls.get_document_detail(db, user, document_id)

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

        if not can_manage_document(user, doc):
            raise ForbiddenError(
                code="FORBIDDEN",
                message="Bạn không có quyền cập nhật metadata cho tài liệu này.",
            )

        before_acl = {
            "department": doc.department,
            "access_scope": doc.access_scope,
            "authorized_role": doc.authorized_role,
        }
        if data.access_scope is not None:
            normalized_scope = data.access_scope.upper().strip()
            if normalized_scope not in {"COMPANY_WIDE", "DEPARTMENT", "ROLE", "RESTRICTED"}:
                raise AppException(status_code=422, code="INVALID_ACCESS_SCOPE", message="access_scope không hợp lệ.")
            if normalized_role(user) == DEPARTMENT_MANAGER and normalized_scope not in {"DEPARTMENT", "RESTRICTED"}:
                raise ForbiddenError(code="SCOPE_MANAGEMENT_DENIED", message="Quản lý phòng ban không được mở tài liệu ra ngoài phòng mình.")
            doc.access_scope = normalized_scope
        if data.department is not None:
            if normalized_role(user) == DEPARTMENT_MANAGER and not same_department(user, data.department):
                raise ForbiddenError(code="DEPARTMENT_SCOPE_DENIED", message="Bạn không được chuyển tài liệu sang phòng ban khác.")
            doc.department = data.department.upper().strip()
        if data.authorized_role is not None:
            doc.authorized_role = data.authorized_role.upper().strip() or None
        if doc.access_scope == "ROLE" and not doc.authorized_role:
            raise AppException(
                status_code=422, code="AUTHORIZED_ROLE_REQUIRED", message="ROLE yêu cầu authorized_role."
            )
        if doc.access_scope != "ROLE":
            doc.authorized_role = None

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
        after_acl = {
            "department": doc.department,
            "access_scope": doc.access_scope,
            "authorized_role": doc.authorized_role,
        }
        if after_acl != before_acl:
            db.add(
                AuditLogDB(
                    tenant=doc.tenant,
                    actor_id=uuid.UUID(str(user["user_id"])),
                    action="DOCUMENT_ACL_UPDATED",
                    resource_type="document",
                    resource_id=str(doc.id),
                    before_state=before_acl,
                    after_state=after_acl,
                )
            )
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

        if not can_manage_document(user, doc):
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

        document = await db.get(DocumentDB, job.document_id)
        if document is None or not can_manage_document(user, document):
            raise ForbiddenError(code="DEPARTMENT_SCOPE_DENIED", message="Bạn không có quyền xem tác vụ của tài liệu này.")

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
            "chunk_count": job.chunk_count,
            "error": job.error,
            "poll_after_ms": 1000,
        }
