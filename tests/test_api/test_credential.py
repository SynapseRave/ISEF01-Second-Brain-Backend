from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.main import app

_USER_ID = "test-user-123"
_TOKEN_PAYLOAD = {"sub": _USER_ID}

_NOTION_PAYLOAD = {
    "service": "notion",
    "credentials": {"api_token": "secret_abc123"},
}
_TODOIST_PAYLOAD = {
    "service": "todoist",
    "credentials": {"api_token": "todoist_token_xyz"},
}
_OBSIDIAN_PAYLOAD = {
    "service": "obsidian",
    "credentials": {"api_key": "obsidian_key", "base_url": "http://localhost:27123"},
}
_GOOGLE_PAYLOAD = {
    "service": "google_calendar",
    "credentials": {
        "access_token": "ya29.google",
        "refresh_token": "1//refresh",
        "expires_at": "2030-01-01T00:00:00Z",
    },
}
_ONENOTE_PAYLOAD = {
    "service": "onenote",
    "credentials": {
        "access_token": "ms_access",
        "refresh_token": "ms_refresh",
        "expires_at": "2030-01-01T00:00:00Z",
    },
}


@pytest.fixture
async def cred_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with test DB and JWT mocked."""
    from unittest.mock import patch

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


# ---------------------------------------------------------------------------
# Auth failures
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/credential/applications/")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_update_requires_auth(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/credential/applications/notion",
        json={"credentials": {"api_token": "x"}},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_delete_requires_auth(client: AsyncClient) -> None:
    resp = await client.delete("/api/credential/applications/notion")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET — list credentials
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_credentials_empty(cred_client: AsyncClient) -> None:
    resp = await cred_client.get("/api/credential/applications/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_credentials_after_create(cred_client: AsyncClient) -> None:
    await cred_client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    resp = await cred_client.get("/api/credential/applications/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["service"] == "notion"
    assert data[0]["configured"] is True
    assert "credentials" not in data[0]


# ---------------------------------------------------------------------------
# POST — create credential
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        _NOTION_PAYLOAD,
        _TODOIST_PAYLOAD,
        _OBSIDIAN_PAYLOAD,
        _GOOGLE_PAYLOAD,
        _ONENOTE_PAYLOAD,
    ],
    ids=["notion", "todoist", "obsidian", "google_calendar", "onenote"],
)
async def test_create_credential_happy_path(
    cred_client: AsyncClient, payload: dict
) -> None:
    resp = await cred_client.post("/api/credential/applications/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["service"] == payload["service"]
    assert data["configured"] is True
    assert "credentials" not in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.anyio
async def test_create_credential_conflict(cred_client: AsyncClient) -> None:
    await cred_client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    resp = await cred_client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_create_credential_invalid_fields(cred_client: AsyncClient) -> None:
    resp = await cred_client.post(
        "/api/credential/applications/",
        json={"service": "notion", "credentials": {"wrong_field": "value"}},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_credential_unknown_service(cred_client: AsyncClient) -> None:
    resp = await cred_client.post(
        "/api/credential/applications/",
        json={"service": "unknown_app", "credentials": {"api_token": "x"}},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT — update credential
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_credential_happy_path(cred_client: AsyncClient) -> None:
    await cred_client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    resp = await cred_client.put(
        "/api/credential/applications/notion",
        json={"credentials": {"api_token": "new_secret_token"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "notion"
    assert data["configured"] is True


@pytest.mark.anyio
async def test_update_credential_not_found(cred_client: AsyncClient) -> None:
    resp = await cred_client.put(
        "/api/credential/applications/notion",
        json={"credentials": {"api_token": "x"}},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_credential_invalid_fields(cred_client: AsyncClient) -> None:
    await cred_client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    resp = await cred_client.put(
        "/api/credential/applications/notion",
        json={"credentials": {"wrong_field": "x"}},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE — remove credential
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_credential_happy_path(cred_client: AsyncClient) -> None:
    await cred_client.post("/api/credential/applications/", json=_NOTION_PAYLOAD)
    resp = await cred_client.delete("/api/credential/applications/notion")
    assert resp.status_code == 204

    list_resp = await cred_client.get("/api/credential/applications/")
    assert list_resp.json() == []


@pytest.mark.anyio
async def test_delete_credential_not_found(cred_client: AsyncClient) -> None:
    resp = await cred_client.delete("/api/credential/applications/notion")
    assert resp.status_code == 404
