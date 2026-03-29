import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.db.models.user_settings import UserSettings
from app.schemas.user import UserProfileResponse, UserUpdate

_KEYCLOAK_ADMIN_TOKEN_URL = (
    f"{settings.keycloak_url}/realms/master/protocol/openid-connect/token"
)
_KEYCLOAK_USERS_URL = (
    f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}/users"
)


async def _get_admin_token() -> str:
    """Obtain a short-lived admin token from Keycloak master realm."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _KEYCLOAK_ADMIN_TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": settings.keycloak_admin_user,
                "password": settings.keycloak_admin_password,
            },
        )
    if response.status_code != 200:
        raise SecondBrainException(
            message="Failed to obtain Keycloak admin token",
            status_code=502,
        )
    return response.json()["access_token"]


async def update_keycloak_user(
    user_id: str, email: str | None, password: str | None
) -> None:
    """Push profile changes to Keycloak via the Admin REST API.

    Args:
        user_id: Keycloak subject ID.
        email: New email address, or None to skip.
        password: New plain-text password, or None to skip.
    """
    admin_token = await _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    async with httpx.AsyncClient() as client:
        if email is not None:
            response = await client.put(
                f"{_KEYCLOAK_USERS_URL}/{user_id}",
                headers=headers,
                json={"email": email, "username": email},
            )
            if response.status_code not in (200, 204):
                raise SecondBrainException(
                    message="Failed to update email in Keycloak",
                    status_code=502,
                )

        if password is not None:
            response = await client.put(
                f"{_KEYCLOAK_USERS_URL}/{user_id}/reset-password",
                headers=headers,
                json={"type": "password", "value": password, "temporary": False},
            )
            if response.status_code not in (200, 204):
                raise SecondBrainException(
                    message="Failed to update password in Keycloak",
                    status_code=502,
                )


def extract_profile_from_token(payload: dict) -> UserProfileResponse:
    """Extract user profile data from a decoded Keycloak JWT payload.

    Args:
        payload: Decoded JWT claims dict.

    Returns:
        Parsed profile data.
    """
    return UserProfileResponse(
        sub=payload.get("sub", ""),
        name=payload.get("name"),
        email=payload.get("email"),
        email_verified=payload.get("email_verified"),
    )


async def get_or_create_settings(db: AsyncSession, user_id: str) -> UserSettings:
    """Load user settings from DB; create a default row if none exists.

    Args:
        db: Active async database session.
        user_id: Keycloak subject ID.

    Returns:
        The user's settings row.
    """
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def update_user_settings(
    db: AsyncSession, user_id: str, payload: UserUpdate
) -> UserSettings:
    """Partially update app-specific user settings in the DB.

    Args:
        db: Active async database session.
        user_id: Keycloak subject ID.
        payload: Fields to update (unset fields are ignored).

    Returns:
        The updated settings row.
    """
    row = await get_or_create_settings(db, user_id)
    settings_fields = {"preferred_llm", "default_targets"}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in settings_fields:
            setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row
