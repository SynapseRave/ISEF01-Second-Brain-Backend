from pydantic import BaseModel, ConfigDict


class UserProfileResponse(BaseModel):
    """User profile data from Keycloak /userinfo endpoint."""

    sub: str
    name: str | None = None
    email: str | None = None
    email_verified: bool | None = None


class UserSettingsData(BaseModel):
    """App-specific user settings stored in the DB."""

    model_config = ConfigDict(from_attributes=True)

    preferred_llm: str | None = None
    default_targets: dict | None = None


class UserResponse(BaseModel):
    """Combined response for GET /api/user and PUT /api/user."""

    profile: UserProfileResponse
    settings: UserSettingsData


class UserSettingsUpdate(BaseModel):
    """Request body for PUT /api/user — all fields optional for partial update."""

    preferred_llm: str | None = None
    default_targets: dict | None = None
