import json
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.user_input import UserInput
from app.main import app

_MOCK_TOKEN_PAYLOAD = {
    "sub": "test-user-123",
    "name": "Test User",
    "email": "test@example.com",
    "email_verified": True,
}


@pytest.fixture
async def input_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with test DB injected and JWT decoding mocked."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with (
        patch(
            "app.api.middleware.auth.decode_token",
            return_value=_MOCK_TOKEN_PAYLOAD,
        ),
        patch(
            "app.api.dependencies.decode_token",
            return_value=_MOCK_TOKEN_PAYLOAD,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as ac:
            yield ac
    del app.dependency_overrides[get_db]


def _parse_sse_events(body: str) -> list[dict]:
    """Extract JSON payloads from an SSE response body."""
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
async def test_post_input_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/api/input/", json={"prompt": "Test"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_input_empty_prompt_returns_422(
    input_client: AsyncClient,
) -> None:
    response = await input_client.post("/api/input/", json={"prompt": "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_input_returns_event_stream(input_client: AsyncClient) -> None:
    response = await input_client.post("/api/input/", json={"prompt": "Termin morgen"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_post_input_stream_contains_done_event(
    input_client: AsyncClient,
) -> None:
    response = await input_client.post("/api/input/", json={"prompt": "Termin morgen"})
    events = _parse_sse_events(response.text)
    types = [e["type"] for e in events]
    assert "done" in types


@pytest.mark.asyncio
async def test_post_input_stream_contains_status_events(
    input_client: AsyncClient,
) -> None:
    response = await input_client.post(
        "/api/input/", json={"prompt": "Notiz erstellen"}
    )
    events = _parse_sse_events(response.text)
    status_events = [e for e in events if e["type"] == "status"]
    assert len(status_events) >= 1


@pytest.mark.asyncio
async def test_post_input_saves_record_to_db(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    prompt = "Aufgabe für nächste Woche anlegen"
    await input_client.post("/api/input/", json={"prompt": prompt})

    result = await db_session.execute(
        select(UserInput).where(UserInput.user_id == "test-user-123")
    )
    records = result.scalars().all()
    assert len(records) == 1
    assert records[0].prompt == prompt


@pytest.mark.asyncio
async def test_post_input_done_event_contains_input_id(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await input_client.post(
        "/api/input/", json={"prompt": "Kalender prüfen"}
    )
    events = _parse_sse_events(response.text)
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert "input_id" in done_events[0]
    assert isinstance(done_events[0]["input_id"], int)
