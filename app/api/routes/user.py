from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_token_payload
from app.schemas.user import UserResponse, UserSettingsData, UserUpdate
from app.services import user as user_service

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/", response_model=UserResponse)
async def get_user(
    token_payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Return Keycloak profile + app settings for the authenticated user."""
    profile = user_service.extract_profile_from_token(token_payload)
    user_settings = await user_service.get_or_create_settings(db, token_payload["sub"])
    return UserResponse(
        profile=profile,
        settings=UserSettingsData.model_validate(user_settings),
    )


@router.put("/", response_model=UserResponse)
async def update_user(
    payload: UserUpdate,
    token_payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update Keycloak profile (email, password) first, then app settings in DB.

    Keycloak is updated first — if it fails, the DB is never touched.
    """
    user_id = token_payload["sub"]

    await user_service.update_keycloak_user(user_id, payload.email, payload.password)
    user_settings = await user_service.update_user_settings(db, user_id, payload)

    profile = user_service.extract_profile_from_token(token_payload)
    if payload.email is not None:
        profile.email = payload.email

    return UserResponse(
        profile=profile,
        settings=UserSettingsData.model_validate(user_settings),
    )
