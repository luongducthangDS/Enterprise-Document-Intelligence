from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.services.citation_service import CitationService

router = APIRouter()


@router.get("/{citation_id}")
async def get_citation_detail(
    citation_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mở chi tiết đoạn trích dẫn tài liệu để đối soát và kiểm chứng."""
    data = await CitationService.get_citation_detail(
        db=db,
        citation_id=citation_id,
        user=current_user,
    )
    return wrap_response(data, request)
