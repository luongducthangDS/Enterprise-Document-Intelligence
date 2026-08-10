from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth_deps import get_current_user
from app.api.dependencies.db_deps import get_db
from app.schemas.common import wrap_response
from app.schemas.evaluation import EvaluationRunRequest
from app.services.evaluation_service import EvaluationService

router = APIRouter()


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_evaluation_run(
    request: Request,
    payload: EvaluationRunRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tạo tác vụ chạy đánh giá chất lượng bộ câu hỏi RAG (Evaluation Run)."""
    data = await EvaluationService.create_evaluation_run(
        db=db,
        user=current_user,
        request_data=payload,
    )
    return wrap_response(data, request)


@router.get("/runs/{run_id}")
async def get_evaluation_run_status(
    run_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Theo dõi tiến độ & kết quả các chỉ số của đợt đánh giá chất lượng."""
    data = await EvaluationService.get_evaluation_run_status(
        db=db,
        user=current_user,
        run_id=run_id,
    )
    return wrap_response(data, request)
