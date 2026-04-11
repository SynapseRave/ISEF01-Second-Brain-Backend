import json

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.credential import UserCredential
from app.schemas.credential import (
    ApplicationCredentialCreate,
    ApplicationCredentialResponse,
    ApplicationCredentialUpdate,
    ApplicationService,
    get_credentials_schema,
)
from app.services.vault.base import VaultService


def _credential_path(user_id: str, service: ApplicationService) -> str:
    return f"{user_id}/{service.value}"


def _validate_credentials(service: ApplicationService, raw: dict) -> dict:
    """Validate raw credentials dict against the service-specific schema.

    Args:
        service: The target external service.
        raw: Unvalidated credentials dict from the request body.

    Returns:
        Validated and serialised credentials dict.

    Raises:
        HTTPException: 422 if validation fails.
    """
    schema = get_credentials_schema(service)
    try:
        parsed = schema.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc
    return parsed.model_dump(mode="json")


def _row_to_response(row: UserCredential) -> ApplicationCredentialResponse:
    return ApplicationCredentialResponse(
        service=ApplicationService(row.service),
        configured=True,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_credentials(
    db: AsyncSession,
    user_id: str,
) -> list[ApplicationCredentialResponse]:
    """Return all configured services for a user (no credential values).

    Args:
        db: Database session.
        user_id: Keycloak subject ID.

    Returns:
        List of configured application credential summaries.
    """
    result = await db.execute(
        select(UserCredential).where(UserCredential.user_id == user_id)
    )
    rows = result.scalars().all()
    return [_row_to_response(row) for row in rows]


async def store_credential(
    db: AsyncSession,
    user_id: str,
    payload: ApplicationCredentialCreate,
    vault: VaultService,
) -> ApplicationCredentialResponse:
    """Store a new application credential (fails with 409 if already configured).

    Args:
        db: Database session.
        user_id: Keycloak subject ID.
        payload: Create request containing service and raw credentials.
        vault: Vault backend for encryption.

    Returns:
        Credential response with no decrypted values.

    Raises:
        HTTPException: 409 if a credential for this service already exists.
        HTTPException: 422 if the credentials fail schema validation.
    """
    validated = _validate_credentials(payload.service, payload.credentials)

    existing = await db.execute(
        select(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.service == payload.service.value,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Credential for '{payload.service.value}' already exists."
                " Use PUT to update."
            ),
        )

    path = _credential_path(user_id, payload.service)
    await vault.store(path, json.dumps(validated))

    row = await db.execute(
        select(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.service == payload.service.value,
        )
    )
    return _row_to_response(row.scalar_one())


async def update_credential(
    db: AsyncSession,
    user_id: str,
    service: ApplicationService,
    payload: ApplicationCredentialUpdate,
    vault: VaultService,
) -> ApplicationCredentialResponse:
    """Update an existing application credential (fails with 404 if not configured).

    Args:
        db: Database session.
        user_id: Keycloak subject ID.
        service: The service whose credential to update.
        payload: Update request containing new raw credentials.
        vault: Vault backend for encryption.

    Returns:
        Updated credential response with no decrypted values.

    Raises:
        HTTPException: 404 if no credential exists for this service.
        HTTPException: 422 if the credentials fail schema validation.
    """
    validated = _validate_credentials(service, payload.credentials)

    existing = await db.execute(
        select(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.service == service.value,
        )
    )
    if existing.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No credential configured for '{service.value}'. Use POST to create."
            ),
        )

    path = _credential_path(user_id, service)
    await vault.store(path, json.dumps(validated))

    row = await db.execute(
        select(UserCredential).where(
            UserCredential.user_id == user_id,
            UserCredential.service == service.value,
        )
    )
    return _row_to_response(row.scalar_one())


async def delete_credential(
    db: AsyncSession,
    user_id: str,
    service: ApplicationService,
    vault: VaultService,
) -> None:
    """Delete an application credential (fails with 404 if not configured).

    Args:
        db: Database session.
        user_id: Keycloak subject ID.
        service: The service whose credential to remove.
        vault: Vault backend for deletion.

    Raises:
        HTTPException: 404 if no credential exists for this service.
    """
    path = _credential_path(user_id, service)
    try:
        await vault.delete(path)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credential configured for '{service.value}'.",
        )
