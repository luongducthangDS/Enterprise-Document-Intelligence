from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user, require_role
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.schemas.document_submissions import DocumentPublicUrlUpdate, SubmissionReviewRequest
from app.services.document_submission_service import DocumentSubmissionService

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_submission(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str | None = Form(None),
    department: str | None = Form(None),
    version: str | None = Form(None),
    effective_date: str | None = Form(None),
    confidentiality: str | None = Form(None),
    access_scope: str = Form("RESTRICTED"),
    authorized_role: str | None = Form(None),
    public_url: str | None = Form(None),
    current_user: dict[str, Any] = Depends(require_role(["DEPARTMENT_MANAGER", "SUPER_ADMIN"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DocumentSubmissionService.create_submission(
        db,
        current_user,
        file,
        title=title,
        category=category,
        department=department,
        version=version,
        effective_date=effective_date,
        confidentiality=confidentiality,
        access_scope=access_scope,
        authorized_role=authorized_role,
        public_url=public_url,
    )
    return wrap_response(data, request)


@router.get("")
async def list_submissions(
    request: Request,
    submission_status: str | None = None,
    current_user: dict[str, Any] = Depends(require_role(["DEPARTMENT_MANAGER", "SUPER_ADMIN"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DocumentSubmissionService.list_submissions(db, current_user, submission_status)
    return wrap_response(data, request)


@router.get("/{submission_id}")
async def get_submission(
    submission_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DocumentSubmissionService.get_submission(db, current_user, submission_id)
    return wrap_response(data, request)


@router.post("/{submission_id}/approve")
async def approve_submission(
    submission_id: str,
    request: Request,
    payload: SubmissionReviewRequest | None = None,
    current_user: dict[str, Any] = Depends(require_role(["DEPARTMENT_MANAGER", "SUPER_ADMIN"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DocumentSubmissionService.approve(
        db, current_user, submission_id, payload.note if payload else None
    )
    return wrap_response(data, request)


@router.post("/{submission_id}/reject")
async def reject_submission(
    submission_id: str,
    request: Request,
    payload: SubmissionReviewRequest | None = None,
    current_user: dict[str, Any] = Depends(require_role(["DEPARTMENT_MANAGER", "SUPER_ADMIN"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await DocumentSubmissionService.reject(
        db, current_user, submission_id, payload.note if payload else None
    )
    return wrap_response(data, request)


@router.patch("/{submission_id}/public-url")
async def update_submission_public_url(
    submission_id: str,
    payload: DocumentPublicUrlUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật public CDN URL (Cloudinary) cho tài liệu chờ duyệt."""
    data = await DocumentSubmissionService.update_public_url(
        db=db,
        user=current_user,
        submission_id=submission_id,
        public_url=payload.public_url,
    )
    return wrap_response(data, request)

