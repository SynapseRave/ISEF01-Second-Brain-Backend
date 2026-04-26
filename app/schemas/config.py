from pydantic import BaseModel


class OAuthConfigResponse(BaseModel):
    """Public OAuth app credentials for frontend integrations."""

    google_calendar_client_id: str
    microsoft_client_id: str
    microsoft_tenant_id: str
