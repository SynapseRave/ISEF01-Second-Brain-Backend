import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedException

_jwks_cache: dict | None = None


async def get_jwks() -> dict:
    """Fetch Keycloak JWKS (JSON Web Key Set) and cache it."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache


async def decode_token(token: str) -> dict:
    """Validate and decode a Keycloak JWT.

    Args:
        token: Raw JWT string (without 'Bearer ' prefix).

    Returns:
        Decoded token claims.

    Raises:
        UnauthorizedException: If the token is invalid or expired.
    """
    try:
        jwks = await get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
        )
        return payload
    except JWTError as e:
        raise UnauthorizedException(f"Invalid token: {e}") from e
