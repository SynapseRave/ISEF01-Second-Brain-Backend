from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.database import get_db

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """Extract and validate the Keycloak JWT, returning the user ID (sub claim).

    Args:
        credentials: Bearer token from the Authorization header.

    Returns:
        The user's Keycloak subject ID.
    """
    payload = await decode_token(credentials.credentials)
    return payload["sub"]


async def get_db_session(
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[AsyncSession, None]:
    """Re-export get_db as a named dependency for route usage."""
    yield db
