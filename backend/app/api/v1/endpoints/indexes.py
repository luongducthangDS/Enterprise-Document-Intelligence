from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import require_role
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.schemas.indexes import IndexRebuildRequest
from app.services.index_service import IndexService

router = APIRouter()


@router.post("/rebuilds", status_code=status.HTTP_202_ACCEPTED)
async def create_index_rebuild_job(
    request: Request,
    payload: IndexRebuildRequest,
    current_user: dict[str, Any] = Depends(require_role(["DEPARTMENT_MANAGER", "SUPER_ADMIN"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tạo tác vụ tái lập chỉ mục (Re-index vector store)."""
    data = await IndexService.create_rebuild_job(
        db=db,
        user=current_user,
        request_data=payload,
    )
    return wrap_response(data, request)


@router.get("/rebuilds/{job_id}")
async def get_index_rebuild_job_status(
    job_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(require_role(["DEPARTMENT_MANAGER", "SUPER_ADMIN"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Theo dõi trạng thái & tiến độ tác vụ tái lập chỉ mục."""
    data = await IndexService.get_rebuild_job_status(
        db=db,
        user=current_user,
        job_id=job_id,
    )
    return wrap_response(data, request)
