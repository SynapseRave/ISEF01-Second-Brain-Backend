import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_check_requires_no_auth(client: AsyncClient) -> None:
    """Health endpoint must be reachable without any Authorization header."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_protected_route_without_token_returns_401(client: AsyncClient) -> None:
    """Any non-health route without a Bearer token must return 401 (auth middleware)."""
    response = await client.get("/api/input")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_with_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    """Any non-health route with a malformed token must return 401."""
    response = await client.get(
        "/api/input", headers={"Authorization": "Bearer not-a-valid-jwt"}
    )
    assert response.status_code == 401
