from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ApplicationService(str, Enum):  # noqa: UP042
    """Supported external application integrations."""

    notion = "notion"
    todoist = "todoist"
    obsidian = "obsidian"
    google_calendar = "google_calendar"
    onenote = "onenote"


# --- per-service credential payloads ---


class NotionCredentials(BaseModel):
    """Notion integration token."""

    api_token: str = Field(..., min_length=1)


class TodoistCredentials(BaseModel):
    """Todoist personal API token."""

    api_token: str = Field(..., min_length=1)


class ObsidianCredentials(BaseModel):
    """Obsidian Local REST API plugin credentials."""

    api_key: str = Field(..., min_length=1)
    base_url: str = Field(default="http://localhost:27123")


class GoogleCalendarCredentials(BaseModel):
    """Google Calendar OAuth2 tokens (obtained by the frontend)."""

    access_token: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)
    expires_at: datetime


class OneNoteCredentials(BaseModel):
    """Microsoft OneNote OAuth2 tokens (obtained by the frontend)."""

    access_token: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)
    expires_at: datetime


AnyCredentials = Annotated[
    NotionCredentials
    | TodoistCredentials
    | ObsidianCredentials
    | GoogleCalendarCredentials
    | OneNoteCredentials,
    Field(discriminator=None),
]

# Map service enum → expected credentials schema
_SERVICE_SCHEMA: dict[ApplicationService, type[BaseModel]] = {
    ApplicationService.notion: NotionCredentials,
    ApplicationService.todoist: TodoistCredentials,
    ApplicationService.obsidian: ObsidianCredentials,
    ApplicationService.google_calendar: GoogleCalendarCredentials,
    ApplicationService.onenote: OneNoteCredentials,
}


def get_credentials_schema(service: ApplicationService) -> type[BaseModel]:
    """Return the Pydantic schema class for the given service.

    Args:
        service: The external application service.

    Returns:
        The corresponding Pydantic model class.
    """
    return _SERVICE_SCHEMA[service]


# --- request / response schemas ---


class ApplicationCredentialCreate(BaseModel):
    """Request body for storing a new application credential."""

    service: ApplicationService
    credentials: dict


class ApplicationCredentialUpdate(BaseModel):
    """Request body for updating an existing application credential."""

    credentials: dict


class ApplicationCredentialResponse(BaseModel):
    """Response schema — never exposes decrypted credential values."""

    model_config = ConfigDict(from_attributes=True)

    service: ApplicationService
    configured: bool
    created_at: datetime
    updated_at: datetime
