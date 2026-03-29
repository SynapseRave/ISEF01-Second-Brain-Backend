from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session, get_token
from app.schemas.user import UserResponse, UserSettingsData, UserSettingsUpdate
from app.services import user as user_service

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/", response_model=UserResponse)
async def get_user(
    token: str = Depends(get_token),
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Return Keycloak profile + app settings for the authenticated user."""
    profile = await user_service.fetch_keycloak_profile(token)
    user_settings = await user_service.get_or_create_settings(db, current_user)
    return UserResponse(
        profile=profile,
        settings=UserSettingsData.model_validate(user_settings),
    )


@router.put("/", response_model=UserResponse)
async def update_user(
    payload: UserSettingsUpdate,
    token: str = Depends(get_token),
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update app-specific settings for the authenticated user."""
    user_settings = await user_service.update_user_settings(db, current_user, payload)
    profile = await user_service.fetch_keycloak_profile(token)
    return UserResponse(
        profile=profile,
        settings=UserSettingsData.model_validate(user_settings),
    )
