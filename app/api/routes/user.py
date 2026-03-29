from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_token_payload
from app.schemas.user import UserResponse, UserSettingsData, UserSettingsUpdate
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
    payload: UserSettingsUpdate,
    token_payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update app-specific settings for the authenticated user."""
    user_settings = await user_service.update_user_settings(
        db, token_payload["sub"], payload
    )
    profile = user_service.extract_profile_from_token(token_payload)
    return UserResponse(
        profile=profile,
        settings=UserSettingsData.model_validate(user_settings),
    )
