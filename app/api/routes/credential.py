from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.schemas.credential import (
    ApplicationCredentialCreate,
    ApplicationCredentialResponse,
    ApplicationCredentialUpdate,
    ApplicationService,
)
from app.services import credential as credential_service
from app.services.vault import get_vault_service
from app.services.vault.base import VaultService

router = APIRouter(prefix="/api/credential/applications", tags=["credentials"])


async def _get_vault(
    db: AsyncSession = Depends(get_db_session),
) -> VaultService:
    return get_vault_service(db)


@router.get("/", response_model=list[ApplicationCredentialResponse])
async def list_application_credentials(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[ApplicationCredentialResponse]:
    """Return all configured external service credentials for the current user.

    Credential values are never included in the response.
    """
    return await credential_service.list_credentials(db, user_id)


@router.post(
    "/",
    response_model=ApplicationCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_credential(
    payload: ApplicationCredentialCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    vault: VaultService = Depends(_get_vault),
) -> ApplicationCredentialResponse:
    """Store a new application credential.

    Returns 409 if a credential for that service already exists.
    Use PUT to update an existing credential.
    """
    return await credential_service.store_credential(db, user_id, payload, vault)


@router.put("/{service}", response_model=ApplicationCredentialResponse)
async def update_application_credential(
    service: ApplicationService,
    payload: ApplicationCredentialUpdate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    vault: VaultService = Depends(_get_vault),
) -> ApplicationCredentialResponse:
    """Update an existing application credential.

    Returns 404 if no credential has been stored for that service yet.
    Use POST to create a new credential.
    """
    return await credential_service.update_credential(
        db, user_id, service, payload, vault
    )


@router.delete("/{service}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application_credential(
    service: ApplicationService,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    vault: VaultService = Depends(_get_vault),
) -> None:
    """Delete an application credential.

    Returns 404 if no credential has been stored for that service.
    """
    await credential_service.delete_credential(db, user_id, service, vault)
