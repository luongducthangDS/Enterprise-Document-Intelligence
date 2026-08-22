from pydantic import BaseModel, Field


class UserAccessUpdate(BaseModel):
    role: str = Field(..., min_length=1, max_length=64)
    department: str = Field(..., min_length=1, max_length=128)