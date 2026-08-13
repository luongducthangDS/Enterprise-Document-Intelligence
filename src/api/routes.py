import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, status

from src.agents.service import answer as agent_answer
from src.agents.service import sanitize_citations
from src.config import get_settings
from src.models.schemas import (
    AgentAnswer,
    AgentQueryRequest,
    ChatRequest,
    ChatResponse,
    EvaluationJobRequest,
    IndexRebuildJobRequest,
    IngestionJobRequest,
    JobAcceptedResponse,
    JobStatusResponse,
)
from src.workers.evaluation import run_evaluation
from src.workers.indexing import run_index_rebuild
from src.workers.ingestion import run_ingestion
from src.workers.jobs import JobExistsError, JobKind, JobRunner, get_job_store

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_service_token(x_service_token: str | None) -> None:
    expected = get_settings().agent_service_token
    if expected and (not x_service_token or not secrets.compare_digest(x_service_token, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")


@router.post("/agent/query", response_model=AgentAnswer)
async def query_agent(
    request: AgentQueryRequest,
    x_service_token: str | None = Header(default=None),
) -> AgentAnswer:
    """Internal Backend-to-Agent contract. Identity fields are trace context only."""
    _verify_service_token(x_service_token)
    logger.info("Processing agent request %s for user %s", request.request_id, request.user_id)
    history = [turn.model_dump() for turn in request.history]
    return await agent_answer(request.query, history=history)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_service_token: str | None = Header(default=None),
) -> ChatResponse:
    """Legacy internal route, giữ cho tương thích ngược. Contract chính thức là
    /agent/query. Yêu cầu service token giống các route internal khác để agent
    không bị gọi trực tiếp nếu vô tình có public ingress.

    Xem docs/AGENT_API.md cho ý nghĩa từng trường trả về (đặc biệt
    escalate/ticket_draft — backend phải tự insert ticket khi escalate=True,
    agent KHÔNG ghi Supabase)."""
    _verify_service_token(x_service_token)
    try:
        history = [h.model_dump() for h in request.history]
        result = await agent_answer(request.message, history=history)
        response = result.model_dump()
        response["citations"] = [item.model_dump() for item in sanitize_citations(response["citations"])]
        return ChatResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}


# --- Worker jobs (internal) ------------------------------------------------
# Backend sở hữu bảng job + lifecycle nghiệp vụ; agent sở hữu execution. Backend
# submit job kèm job_id của mình rồi poll GET /agent/jobs/{job_id} và mirror
# state/stage/progress vào DB. Contract đầy đủ: docs/rag-pipeline/AGENT_WORKERS.md.

_POLL_AFTER_MS: dict[str, int] = {"INGESTION": 1000, "INDEX_REBUILD": 2000, "EVALUATION": 3000}


def _submit_job(kind: JobKind, job_id: str, runner: JobRunner) -> JobAcceptedResponse:
    try:
        record = get_job_store().submit(kind, runner, job_id=job_id)
    except JobExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info("Nhận job %s (%s)", record.job_id, kind)
    return JobAcceptedResponse(
        job_id=record.job_id,
        kind=kind,
        state=record.state,
        poll_after_ms=_POLL_AFTER_MS[kind],
    )


@router.post("/agent/jobs/ingestion", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_ingestion_job(
    request: IngestionJobRequest,
    x_service_token: str | None = Header(default=None),
) -> JobAcceptedResponse:
    """Parse -> chunk -> embed -> index 1 tài liệu Backend upload lên."""
    _verify_service_token(x_service_token)
    return _submit_job("INGESTION", request.job_id, lambda progress: run_ingestion(request, progress))


@router.post("/agent/jobs/index-rebuild", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_index_rebuild_job(
    request: IndexRebuildJobRequest,
    x_service_token: str | None = Header(default=None),
) -> JobAcceptedResponse:
    """Nạp lại chunk đã có vào vector DB (không parse lại tài liệu)."""
    _verify_service_token(x_service_token)
    return _submit_job("INDEX_REBUILD", request.job_id, lambda progress: run_index_rebuild(request, progress))


@router.post("/agent/jobs/evaluation", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_evaluation_job(
    request: EvaluationJobRequest,
    x_service_token: str | None = Header(default=None),
) -> JobAcceptedResponse:
    """Chạy bộ eval qua agent thật, trả metrics + quality gate."""
    _verify_service_token(x_service_token)
    return _submit_job("EVALUATION", request.job_id, lambda progress: run_evaluation(request, progress))


@router.get("/agent/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    x_service_token: str | None = Header(default=None),
) -> JobStatusResponse:
    _verify_service_token(x_service_token)
    record = get_job_store().get(job_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Không tìm thấy job {job_id}")
    return JobStatusResponse(
        job_id=record.job_id,
        kind=record.kind,
        state=record.state,
        stage=record.stage,
        progress_percent=record.progress_percent,
        result=record.result,
        error=record.error,
        poll_after_ms=_POLL_AFTER_MS.get(record.kind, 2000),
    )
