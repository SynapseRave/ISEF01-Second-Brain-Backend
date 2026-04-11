import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.user_input import UserInput
from app.main import app
from app.services.input import save_input

_MOCK_TOKEN_PAYLOAD = {
    "sub": "test-user-123",
    "name": "Test User",
    "email": "test@example.com",
    "email_verified": True,
}

_OTHER_USER_ID = "other-user-456"


@pytest.fixture(autouse=True)
def mock_llm() -> None:
    """Replace the LLM service with a stub that yields two fixed tokens."""

    async def _fake_stream(history, prompt):
        yield "Antwort "
        yield "Text"

    fake_svc = MagicMock()
    fake_svc.stream_response = _fake_stream
    fake_svc.model_name = "test-model"

    with patch("app.services.input.get_llm_service", return_value=fake_svc):
        yield


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
    app.dependency_overrides.pop(get_db, None)


def _parse_sse_events(body: str) -> list[dict]:
    """Extract JSON payloads from an SSE response body."""
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


# ---------------------------------------------------------------------------
# POST /api/input/
# ---------------------------------------------------------------------------


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
    assert records[0].response == "Antwort Text"
    assert records[0].model == "test-model"


@pytest.mark.asyncio
async def test_post_input_stream_contains_chunk_events(
    input_client: AsyncClient,
) -> None:
    response = await input_client.post("/api/input/", json={"prompt": "Test"})
    events = _parse_sse_events(response.text)
    chunks = [e for e in events if e["type"] == "chunk"]
    assert len(chunks) >= 1
    assert all("text" in e for e in chunks)


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


@pytest.mark.asyncio
async def test_post_input_done_event_contains_conversation_id(
    input_client: AsyncClient,
) -> None:
    response = await input_client.post("/api/input/", json={"prompt": "Neue Notiz"})
    events = _parse_sse_events(response.text)
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    cid = done_events[0].get("conversation_id")
    assert cid is not None
    uuid.UUID(cid)  # must be a valid UUID string


@pytest.mark.asyncio
async def test_post_input_with_conversation_id_appends_to_thread(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    # First message – creates a new conversation
    r1 = await input_client.post("/api/input/", json={"prompt": "Erste Nachricht"})
    events1 = _parse_sse_events(r1.text)
    cid = [e for e in events1 if e["type"] == "done"][0]["conversation_id"]

    # Second message – continues the conversation
    await input_client.post(
        "/api/input/",
        json={"prompt": "Zweite Nachricht", "conversation_id": cid},
    )

    result = await db_session.execute(
        select(UserInput).where(UserInput.conversation_id == uuid.UUID(cid))
    )
    messages = result.scalars().all()
    assert len(messages) == 2


# ---------------------------------------------------------------------------
# GET /api/input/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_inputs_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/input/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_inputs_empty_returns_empty_list(
    input_client: AsyncClient,
) -> None:
    response = await input_client.get("/api/input/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["pages"] == 0


@pytest.mark.asyncio
async def test_list_inputs_returns_only_own_inputs(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await input_client.post("/api/input/", json={"prompt": "Mein Input"})
    # Insert record for a different user directly via service
    await save_input(db_session, _OTHER_USER_ID, "Fremder Input")

    response = await input_client.get("/api/input/")
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["prompt"] == "Mein Input"


@pytest.mark.asyncio
async def test_list_inputs_pagination(
    input_client: AsyncClient,
) -> None:
    for i in range(5):
        await input_client.post("/api/input/", json={"prompt": f"Input {i}"})

    response = await input_client.get("/api/input/?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["total"] == 5
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_list_inputs_invalid_page_returns_422(
    input_client: AsyncClient,
) -> None:
    response = await input_client.get("/api/input/?page=0")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/input/{input_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_input_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/input/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_input_returns_correct_record(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await input_client.post("/api/input/", json={"prompt": "Suche Termin"})
    result = await db_session.execute(
        select(UserInput).where(UserInput.user_id == "test-user-123")
    )
    record = result.scalars().first()
    assert record is not None

    response = await input_client.get(f"/api/input/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == "Suche Termin"
    assert data["id"] == record.id


@pytest.mark.asyncio
async def test_get_input_not_found_returns_404(
    input_client: AsyncClient,
) -> None:
    response = await input_client.get("/api/input/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_input_other_users_record_returns_404(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = await save_input(db_session, _OTHER_USER_ID, "Geheimer Input")
    response = await input_client.get(f"/api/input/{record.id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/input/conversations/{conversation_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_without_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/api/input/conversations/{uuid.uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_conversation_returns_messages_in_order(
    input_client: AsyncClient,
) -> None:
    r1 = await input_client.post("/api/input/", json={"prompt": "Nachricht 1"})
    cid = [e for e in _parse_sse_events(r1.text) if e["type"] == "done"][0][
        "conversation_id"
    ]

    await input_client.post(
        "/api/input/",
        json={"prompt": "Nachricht 2", "conversation_id": cid},
    )

    response = await input_client.get(f"/api/input/conversations/{cid}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    prompts = [m["prompt"] for m in data["messages"]]
    assert prompts == ["Nachricht 1", "Nachricht 2"]


@pytest.mark.asyncio
async def test_get_conversation_not_found_returns_404(
    input_client: AsyncClient,
) -> None:
    response = await input_client.get(f"/api/input/conversations/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_other_users_conversation_returns_404(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = await save_input(db_session, _OTHER_USER_ID, "Geheime Konversation")
    cid = str(record.conversation_id)
    response = await input_client.get(f"/api/input/conversations/{cid}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/input/{input_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_input_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.delete("/api/input/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_input_returns_204(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await input_client.post("/api/input/", json={"prompt": "Zu löschende Notiz"})
    result = await db_session.execute(
        select(UserInput).where(UserInput.user_id == "test-user-123")
    )
    record = result.scalars().first()
    assert record is not None

    response = await input_client.delete(f"/api/input/{record.id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_input_removes_from_db(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await input_client.post("/api/input/", json={"prompt": "Wird gelöscht"})
    result = await db_session.execute(
        select(UserInput).where(UserInput.user_id == "test-user-123")
    )
    record = result.scalars().first()
    assert record is not None
    record_id = record.id

    await input_client.delete(f"/api/input/{record_id}")

    db_session.expire_all()
    result = await db_session.execute(
        select(UserInput).where(UserInput.id == record_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_input_not_found_returns_404(
    input_client: AsyncClient,
) -> None:
    response = await input_client.delete("/api/input/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_input_other_users_record_returns_404(
    input_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    record = await save_input(db_session, _OTHER_USER_ID, "Fremder Input")
    response = await input_client.delete(f"/api/input/{record.id}")
    assert response.status_code == 404
