from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import OAuth2AuthorizationCodeBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.database import get_db

_oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=(
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/auth"
    ),
    tokenUrl=(
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/token"
    ),
)


async def get_token(token: str = Depends(_oauth2_scheme)) -> str:
    """Return the raw Bearer token from the Authorization header.

    Args:
        token: JWT string extracted by the OAuth2 scheme.

    Returns:
        The raw JWT string.
    """
    return token


async def get_current_user(token: str = Depends(_oauth2_scheme)) -> str:
    """Extract and validate the Keycloak JWT, returning the user ID (sub claim).

    Args:
        token: JWT string extracted by the OAuth2 scheme.

    Returns:
        The user's Keycloak subject ID.
    """
    payload = await decode_token(token)
    return payload["sub"]


async def get_db_session(
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[AsyncSession, None]:
    """Re-export get_db as a named dependency for route usage."""
    yield db
