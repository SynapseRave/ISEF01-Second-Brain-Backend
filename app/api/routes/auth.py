from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.schemas.auth import GoogleTokenExchangeRequest, GoogleTokenExchangeResponse
from app.schemas.credential import (
    ApplicationCredentialCreate,
    ApplicationCredentialUpdate,
    ApplicationService,
)
from app.services import auth as auth_service
from app.services import credential as credential_service
from app.services.vault import get_vault_service
from app.services.vault.base import VaultService

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _get_vault(
    db: AsyncSession = Depends(get_db_session),
) -> VaultService:
    return get_vault_service(db)


@router.post("/google/token", response_model=GoogleTokenExchangeResponse)
async def exchange_google_token(
    payload: GoogleTokenExchangeRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    vault: VaultService = Depends(_get_vault),
) -> GoogleTokenExchangeResponse:
    """Exchange a Google authorization code for OAuth tokens.

    The client_secret never leaves the server. The frontend sends only the
    authorization code and PKCE code_verifier obtained during the OAuth flow.
    On success, the tokens are also stored for the current user so the OAuth
    callback completes atomically in a single backend request.
    """
    result = await auth_service.exchange_google_token(
        code=payload.code,
        code_verifier=payload.code_verifier,
        redirect_uri=payload.redirect_uri,
    )

    try:
        await credential_service.update_credential(
            db=db,
            user_id=user_id,
            service=ApplicationService.google_calendar,
            payload=ApplicationCredentialUpdate(credentials=result),
            vault=vault,
        )
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        await credential_service.store_credential(
            db=db,
            user_id=user_id,
            payload=ApplicationCredentialCreate(
                service=ApplicationService.google_calendar,
                credentials=result,
            ),
            vault=vault,
        )

    return GoogleTokenExchangeResponse(connected=True)
