from pydantic import BaseModel, Field


class SubmissionReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class SubmissionMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    department: str | None = Field(default=None, min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=64)
    effective_date: str | None = Field(default=None, max_length=32)
    access_scope: str | None = Field(default=None, min_length=1, max_length=32)
    authorized_role: str | None = Field(default=None, max_length=64)
