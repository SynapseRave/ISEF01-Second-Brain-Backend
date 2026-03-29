from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_settings import UserSettings
from app.schemas.user import UserProfileResponse, UserSettingsUpdate


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
