from fastapi import APIRouter, HTTPException

from src.agents.service import answer as agent_answer
from src.models.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent. Xem docs/AGENT_API.md cho ý nghĩa từng trường trả về
    (đặc biệt escalate/ticket_draft — backend phải tự insert ticket khi
    escalate=True, agent KHÔNG ghi Supabase)."""
    try:
        result = await agent_answer(request.message)
        return ChatResponse(**result.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
