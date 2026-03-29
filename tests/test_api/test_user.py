from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.main import app
from app.schemas.user import UserProfileResponse

_MOCK_PROFILE = UserProfileResponse(
    sub="test-user-123",
    name="Test User",
    email="test@example.com",
    email_verified=True,
)


@pytest.fixture
async def user_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with test DB injected via dependency override."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with patch(
        "app.core.security.decode_token",
        return_value={"sub": "test-user-123"},
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as ac:
            yield ac
    del app.dependency_overrides[get_db]


@pytest.fixture
def mock_keycloak() -> AsyncMock:
    with patch(
        "app.services.user.fetch_keycloak_profile",
        new_callable=AsyncMock,
        return_value=_MOCK_PROFILE,
    ) as mock:
        yield mock


@pytest.mark.asyncio
async def test_get_user_returns_profile_and_settings(
    user_client: AsyncClient,
    mock_keycloak: AsyncMock,
) -> None:
    response = await user_client.get("/api/user/")
    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["sub"] == "test-user-123"
    assert data["profile"]["email"] == "test@example.com"
    assert data["settings"]["preferred_llm"] is None
    assert data["settings"]["default_targets"] is None


@pytest.mark.asyncio
async def test_get_user_auto_creates_settings(
    user_client: AsyncClient,
    mock_keycloak: AsyncMock,
) -> None:
    """First GET auto-creates a default settings row in the DB."""
    response = await user_client.get("/api/user/")
    assert response.status_code == 200
    # Second call should return the same row (not fail with duplicate)
    response2 = await user_client.get("/api/user/")
    assert response2.status_code == 200


@pytest.mark.asyncio
async def test_get_user_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/user/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_put_user_updates_preferred_llm(
    user_client: AsyncClient,
    mock_keycloak: AsyncMock,
) -> None:
    response = await user_client.put("/api/user/", json={"preferred_llm": "openai"})
    assert response.status_code == 200
    assert response.json()["settings"]["preferred_llm"] == "openai"


@pytest.mark.asyncio
async def test_put_user_updates_default_targets(
    user_client: AsyncClient,
    mock_keycloak: AsyncMock,
) -> None:
    payload = {"default_targets": {"note": "notion", "task": "todoist"}}
    response = await user_client.put("/api/user/", json=payload)
    assert response.status_code == 200
    targets = response.json()["settings"]["default_targets"]
    assert targets["note"] == "notion"
    assert targets["task"] == "todoist"


@pytest.mark.asyncio
async def test_put_user_unauthenticated(client: AsyncClient) -> None:
    response = await client.put("/api/user/", json={"preferred_llm": "openai"})
    assert response.status_code == 401
