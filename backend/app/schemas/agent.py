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
    source_type: str = ""
    excerpt: str = ""


class AgentTicketDraftDTO(BaseModel):
    employee_question: str
    escalate_reason: str
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    category: str | None = None
    target_department: str
    priority: Literal["Low", "Medium", "High"]


class AgentAllowedDataFieldDTO(BaseModel):
    field_key: str
    label: str
    required_for_prefill: bool = False
    pii_class: Literal["Low", "Medium", "High", "Critical"]
    storage_policy: Literal["do_not_store", "store_case_only", "store_message_ok", "store_metadata_only"]


class AgentBoundaryDecisionDTO(BaseModel):
    """Canonical runtime decision từ agent — xem Runtime-Revised Canonical
    Scenario Registry trong docs/project/hr_interaction_boundary_plan.md.

    Backend KHÔNG diễn giải lại nghiệp vụ ở đây: nó chỉ chuyển tiếp nguyên vẹn
    cho client. `runtime_action` (mức được phép ngay bây giờ) khác
    `max_runtime_action` (trần theo registry, có thể là CREATE_CASE ở MVP-2) —
    client phải render theo `runtime_action`.
    """

    scenario_id: int | None = None
    scenario_name: str | None = None
    service_code: str | None = None
    service_name: str | None = None
    assistant_role: Literal["ANSWER", "GUIDE", "PREPARE_AND_HANDOFF", "HUMAN_FIRST"]
    sensitivity: Literal["Low", "Medium", "High", "Critical"]
    runtime_source_status: str
    source_of_truth_label: str
    max_runtime_action: Literal["NONE", "LINK_ONLY", "PREFILL_DRAFT", "CREATE_CASE"]
    runtime_action: Literal["NONE", "LINK_ONLY", "PREFILL_DRAFT", "CREATE_CASE"]
    mvp_phase: Literal["MVP_1", "MVP_2", "FUTURE", "OUT_OF_MVP"]
    handoff_target: dict[str, str] | None = None
    user_facing_action_label: str | None = None
    allowed_data_fields: list[AgentAllowedDataFieldDTO] = Field(default_factory=list)
    runtime_behavior: str = ""
    resolution: Literal["registry", "fallback"] = "registry"


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
    # Nullable: agent bản cũ chưa gửi field này, backend vẫn phải chạy được.
    boundary: AgentBoundaryDecisionDTO | None = None

    @model_validator(mode="after")
    def validate_control_fields(self):
        if self.needs_clarification and not (self.clarifying_question or self.response).strip():
            raise ValueError("Clarification result must contain a question")
        if self.escalate and self.ticket_draft is None:
            raise ValueError("Escalated result must contain ticket_draft")
        return self
