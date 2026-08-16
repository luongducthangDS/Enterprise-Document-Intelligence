from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.services.document_service import DocumentService

router = APIRouter()


@router.get("/{job_id}")
async def get_ingestion_job_status(
    job_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Theo dõi trạng thái & tiến độ xử lý trích xuất/chunking/indexing tài liệu."""
    data = await DocumentService.get_ingestion_job(
        db=db,
        user=current_user,
        job_id=job_id,
    )
    return wrap_response(data, request)
