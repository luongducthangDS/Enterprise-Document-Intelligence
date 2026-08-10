from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AgentCitationDTO(BaseModel):
    chunk_id: str
    source_file: str
    title: str
    page_start: int | None = None
    page_end: int | None = None
    category: str
    is_official_policy: bool


class AgentTicketDraftDTO(BaseModel):
    employee_question: str
    escalate_reason: str
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    category: str | None = None
    target_department: str
    priority: Literal["Low", "Medium", "High"]


class AgentAnswerDTO(BaseModel):
    response: str
    intent: Literal["greeting", "hr_question", "ambiguous", "out_of_scope_or_personal"]
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    citations: list[AgentCitationDTO] = Field(default_factory=list)
    needs_clarification: bool = False
    clarifying_question: str | None = None
    escalate: bool = False
    escalate_reason: str | None = None
    ticket_draft: AgentTicketDraftDTO | None = None

    @model_validator(mode="after")
    def validate_control_fields(self):
        if self.needs_clarification and not (self.clarifying_question or self.response).strip():
            raise ValueError("Clarification result must contain a question")
        if self.escalate and self.ticket_draft is None:
            raise ValueError("Escalated result must contain ticket_draft")
        return self
