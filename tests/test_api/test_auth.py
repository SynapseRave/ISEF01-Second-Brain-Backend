from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.main import app

_USER_ID = "test-user-123"
_TOKEN_PAYLOAD = {"sub": _USER_ID}


@pytest.fixture
async def auth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with (
        patch("app.api.middleware.auth.decode_token", return_value=_TOKEN_PAYLOAD),
        patch("app.api.dependencies.decode_token", return_value=_TOKEN_PAYLOAD),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as ac:
            yield ac

    app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_exchange_google_token_persists_credentials(
    auth_client: AsyncClient,
) -> None:
    payload = {
        "code": "google-auth-code",
        "code_verifier": "pkce-verifier",
        "redirect_uri": "http://localhost:3000/settings/connect/callback/google-calendar",
    }
    google_tokens = {
        "access_token": "ya29.google",
        "refresh_token": "1//refresh",
        "expires_in": 3600,
    }

    with (
        patch("app.services.auth.settings") as mock_settings,
        patch("app.services.auth.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.google_calendar_client_secret = "test-secret"
        mock_settings.google_calendar_client_id = "test-client-id"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = google_tokens
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = await auth_client.post("/api/auth/google/token", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True

    list_resp = await auth_client.get("/api/credential/applications/")
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["service"] == "google_calendar"
    assert list_resp.json()[0]["configured"] is True
