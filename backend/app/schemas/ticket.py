from pydantic import BaseModel


class TicketCreate(BaseModel):
    user_query: str
    reason: str
    confidence_score: float | None = None


class TicketResponse(BaseModel):
    id: str
    user_id: str
    user_query: str
    status: str  # OPEN, IN_PROGRESS, RESOLVED
    confidence_score: float | None = None
    created_at: str
