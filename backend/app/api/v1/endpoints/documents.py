from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.schemas.documents import DocumentArchiveRequest, DocumentMetadataUpdate
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str | None = Form(None),
    version: str | None = Form(None),
    effective_date: str | None = Form(None),
    confidentiality: str | None = Form(None),
    status_field: str | None = Form(None, alias="status"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """HR Admin / Người dùng Upload tài liệu chính sách mới (PDF/DOCX/XLSX)."""
    data = await DocumentService.upload_document(
        db=db,
        user=current_user,
        file=file,
        title=title,
        category=category,
        version=version,
        effective_date=effective_date,
        confidentiality=confidentiality,
        status=status_field,
    )
    return wrap_response(data, request)


@router.get("")
async def list_documents(
    request: Request,
    doc_status: str | None = None,
    category: str | None = None,
    ingestion_state: str | None = None,
    indexed: bool | None = None,
    limit: int = 20,
    cursor: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Danh sách tài liệu chính sách có lọc và phân trang."""
    data, pagination = await DocumentService.list_documents(
        db=db,
        user=current_user,
        status=doc_status,
        category=category,
        ingestion_state=ingestion_state,
        indexed=indexed,
        limit=limit,
        cursor=cursor,
    )
    return wrap_response(data, request, pagination=pagination)


@router.get("/{document_id}")
async def get_document_detail(
    document_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lấy chi tiết tài liệu chính sách, thông tin ingestion và trạng thái chỉ mục vector."""
    data = await DocumentService.get_document_detail(
        db=db,
        user=current_user,
        document_id=document_id,
    )
    return wrap_response(data, request)


@router.patch("/{document_id}/metadata")
async def update_document_metadata(
    document_id: str,
    payload: DocumentMetadataUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cập nhật metadata tài liệu chính sách (chỉ dành cho HR Admin / Super Admin)."""
    data = await DocumentService.update_document_metadata(
        db=db,
        user=current_user,
        document_id=document_id,
        data=payload,
    )
    return wrap_response(data, request)


@router.post("/{document_id}/archive")
async def archive_document(
    document_id: str,
    request: Request,
    payload: DocumentArchiveRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lưu trữ mềm (soft archive) tài liệu chính sách."""
    reason = payload.reason if payload else None
    data = await DocumentService.archive_document(
        db=db,
        user=current_user,
        document_id=document_id,
        reason=reason,
    )
    return wrap_response(data, request)
