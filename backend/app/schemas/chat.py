from typing import Optional
from pydantic import BaseModel


class ChatMessageInput(BaseModel):
    query: str
    session_id: Optional[str] = None


class CitationSchema(BaseModel):
    document_title: str
    section: str
    url: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    confidence_score: float
    citations: list[CitationSchema]
    is_escalated: bool = False
    ticket_id: Optional[str] = None
