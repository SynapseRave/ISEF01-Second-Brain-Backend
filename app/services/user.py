import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.db.models.user_settings import UserSettings
from app.schemas.user import UserProfileResponse, UserSettingsUpdate


async def fetch_keycloak_profile(token: str) -> UserProfileResponse:
    """Fetch user profile from Keycloak's OIDC /userinfo endpoint.

    Args:
        token: Raw Bearer token of the authenticated user.

    Returns:
        Parsed profile data from Keycloak.

    Raises:
        SecondBrainException: If Keycloak returns a non-200 response.
    """
    userinfo_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/userinfo"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.status_code != 200:
        raise SecondBrainException(
            message="Failed to fetch user profile from Keycloak",
            status_code=502,
        )
    data = response.json()
    return UserProfileResponse(
        sub=data.get("sub", ""),
        name=data.get("name"),
        email=data.get("email"),
        email_verified=data.get("email_verified"),
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
    db: AsyncSession, user_id: str, payload: UserSettingsUpdate
) -> UserSettings:
    """Partially update user settings in the DB.

    Args:
        db: Active async database session.
        user_id: Keycloak subject ID.
        payload: Fields to update (unset fields are ignored).

    Returns:
        The updated settings row.
    """
    row = await get_or_create_settings(db, user_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row
