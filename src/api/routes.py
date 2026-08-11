import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, status

from src.agents.service import answer as agent_answer
from src.config import get_settings
from src.models.schemas import AgentAnswer, AgentQueryRequest, ChatRequest, ChatResponse

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
    return await agent_answer(request.query)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent. Xem docs/AGENT_API.md cho ý nghĩa từng trường trả về
    (đặc biệt escalate/ticket_draft — backend phải tự insert ticket khi
    escalate=True, agent KHÔNG ghi Supabase)."""
    try:
        history = [h.model_dump() for h in request.history]
        result = await agent_answer(request.message, history=history)
        return ChatResponse(**result.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
