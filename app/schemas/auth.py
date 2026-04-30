from pydantic import BaseModel, Field


class GoogleTokenExchangeRequest(BaseModel):
    """Frontend sends code + PKCE verifier; backend adds client_secret."""

    code: str = Field(..., min_length=1)
    code_verifier: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)


class GoogleTokenExchangeResponse(BaseModel):
    """Successful Google OAuth exchange persisted server-side."""

    connected: bool = True
