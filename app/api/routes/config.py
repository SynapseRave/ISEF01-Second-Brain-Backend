from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.schemas.config import OAuthConfigResponse

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=OAuthConfigResponse)
async def get_oauth_config(
    _: str = Depends(get_current_user),
) -> OAuthConfigResponse:
    """Return the application-level OAuth client IDs for frontend integrations.

    These are app credentials, not user secrets. The user's access/refresh tokens
    are stored separately in the credentials table after the OAuth flow completes.
    """
    return OAuthConfigResponse(
        google_calendar_client_id=settings.google_calendar_client_id,
        microsoft_client_id=settings.microsoft_client_id,
        microsoft_tenant_id=settings.microsoft_tenant_id,
    )
