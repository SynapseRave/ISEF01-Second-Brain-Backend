from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class InputRequest(BaseModel):
    """Request body for POST /api/input."""

    prompt: str

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_empty(cls, v: str) -> str:
        """Reject blank or whitespace-only prompts."""
        if not v.strip():
            raise ValueError("Prompt darf nicht leer sein.")
        return v


class InputResponse(BaseModel):
    """Response schema for a single stored user input."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    prompt: str
    response: str | None
    tool: str | None
    model: str | None
    deep_link: str | None
    created_at: datetime
