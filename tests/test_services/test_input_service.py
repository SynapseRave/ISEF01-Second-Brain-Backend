import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.models.user_input import UserInput
from app.schemas.credential import ApplicationService
from app.services.input import (
    delete_input,
    get_conversation,
    get_input_by_id,
    get_inputs,
    process_input_stream,
    save_input,
)

_USER_A = "user-a"
_USER_B = "user-b"


# ---------------------------------------------------------------------------
# save_input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_input_creates_new_conversation_when_none_given(
    db_session: AsyncSession,
) -> None:
    record = await save_input(db_session, _USER_A, "Test prompt")
    assert record.conversation_id is not None
    assert isinstance(record.conversation_id, uuid.UUID)


@pytest.mark.asyncio
async def test_save_input_uses_provided_conversation_id(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    record = await save_input(db_session, _USER_A, "Folge-Nachricht", cid)
    assert record.conversation_id == cid


@pytest.mark.asyncio
async def test_save_input_appends_to_existing_conversation(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    r1 = await save_input(db_session, _USER_A, "Erste", cid)
    r2 = await save_input(db_session, _USER_A, "Zweite", cid)

    assert r1.conversation_id == r2.conversation_id == cid

    result = await db_session.execute(
        select(UserInput).where(UserInput.conversation_id == cid)
    )
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_save_input_each_new_call_without_cid_gets_different_conversation(
    db_session: AsyncSession,
) -> None:
    r1 = await save_input(db_session, _USER_A, "Erste")
    r2 = await save_input(db_session, _USER_A, "Zweite")
    assert r1.conversation_id != r2.conversation_id


# ---------------------------------------------------------------------------
# get_inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_inputs_returns_only_user_records(
    db_session: AsyncSession,
) -> None:
    await save_input(db_session, _USER_A, "A Prompt")
    await save_input(db_session, _USER_B, "B Prompt")

    records, total = await get_inputs(db_session, _USER_A, page=1, page_size=20)
    assert total == 1
    assert records[0].user_id == _USER_A


@pytest.mark.asyncio
async def test_get_inputs_pagination(
    db_session: AsyncSession,
) -> None:
    for i in range(5):
        await save_input(db_session, _USER_A, f"Prompt {i}")

    records, total = await get_inputs(db_session, _USER_A, page=2, page_size=2)
    assert total == 5
    assert len(records) == 2


@pytest.mark.asyncio
async def test_get_inputs_empty_returns_zero(
    db_session: AsyncSession,
) -> None:
    records, total = await get_inputs(db_session, _USER_A, page=1, page_size=20)
    assert records == []
    assert total == 0


# ---------------------------------------------------------------------------
# get_input_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_input_by_id_returns_record(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_A, "Mein Input")
    record = await get_input_by_id(db_session, _USER_A, saved.id)
    assert record.id == saved.id


@pytest.mark.asyncio
async def test_get_input_by_id_raises_not_found_for_missing_id(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFoundException):
        await get_input_by_id(db_session, _USER_A, 99999)


@pytest.mark.asyncio
async def test_get_input_by_id_raises_not_found_for_wrong_user(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_B, "B's Input")
    with pytest.raises(NotFoundException):
        await get_input_by_id(db_session, _USER_A, saved.id)


# ---------------------------------------------------------------------------
# delete_input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_input_removes_record(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_A, "Zu löschen")
    await delete_input(db_session, _USER_A, saved.id)

    result = await db_session.execute(select(UserInput).where(UserInput.id == saved.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_input_raises_not_found_for_missing_id(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFoundException):
        await delete_input(db_session, _USER_A, 99999)


@pytest.mark.asyncio
async def test_delete_input_raises_not_found_for_wrong_user(
    db_session: AsyncSession,
) -> None:
    saved = await save_input(db_session, _USER_B, "B's Input")
    with pytest.raises(NotFoundException):
        await delete_input(db_session, _USER_A, saved.id)


@pytest.mark.asyncio
async def test_delete_input_does_not_cascade_to_conversation(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    r1 = await save_input(db_session, _USER_A, "Erste", cid)
    r2 = await save_input(db_session, _USER_A, "Zweite", cid)

    await delete_input(db_session, _USER_A, r1.id)

    result = await db_session.execute(select(UserInput).where(UserInput.id == r2.id))
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# get_conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conversation_returns_messages_in_order(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    await save_input(db_session, _USER_A, "Erste", cid)
    await save_input(db_session, _USER_A, "Zweite", cid)

    messages = await get_conversation(db_session, _USER_A, cid)
    assert len(messages) == 2
    assert messages[0].prompt == "Erste"
    assert messages[1].prompt == "Zweite"


@pytest.mark.asyncio
async def test_get_conversation_returns_empty_for_unknown_id(
    db_session: AsyncSession,
) -> None:
    messages = await get_conversation(db_session, _USER_A, uuid.uuid4())
    assert messages == []


@pytest.mark.asyncio
async def test_get_conversation_does_not_return_other_users_messages(
    db_session: AsyncSession,
) -> None:
    cid = uuid.uuid4()
    await save_input(db_session, _USER_B, "B's Nachricht", cid)

    messages = await get_conversation(db_session, _USER_A, cid)
    assert messages == []


# ---------------------------------------------------------------------------
# process_input_stream — MCP integration
# ---------------------------------------------------------------------------


async def _collect_events(gen) -> list[dict]:
    """Drain an SSE generator and parse each JSON event."""
    events = []
    async for raw in gen:
        line = raw.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))
    return events


@pytest.mark.asyncio
async def test_process_input_stream_without_vault_skips_mcp(
    db_session: AsyncSession,
) -> None:
    """When vault=None, the stream should work as before (no MCP calls)."""

    async def _fake_stream(*args, **kwargs):
        yield "Antwort ohne Tools"

    with patch("app.services.input.get_llm_service") as mock_llm_factory:
        mock_llm = MagicMock()
        mock_llm.stream_response = _fake_stream
        mock_llm.model_name = "test-model"
        mock_llm_factory.return_value = mock_llm

        events = await _collect_events(
            process_input_stream(db_session, _USER_A, "Hallo", vault=None)
        )

    types = [e["type"] for e in events]
    assert "chunk" in types
    assert "tool_call" not in types
    assert "done" in types


@pytest.mark.asyncio
async def test_process_input_stream_with_tools_emits_tool_call_event(
    db_session: AsyncSession,
) -> None:
    """When vault is set and LLM returns a tool call, a tool_call event is emitted."""
    from app.services.llm.base import LLMResponse, ToolCall
    from app.services.mcp.client import ToolCallResult

    tool_call = ToolCall(
        id="tc_1", name="notion__create_page", arguments={"title": "T"}
    )
    mcp_result = ToolCallResult(
        tool_name="create_page",
        service=ApplicationService.notion,
        content=[{"type": "text", "text": "Erstellt!\ndeep_link: https://notion.so/x"}],
        is_error=False,
        deep_link="https://notion.so/x",
    )

    async def _fake_stream(*args, **kwargs):
        yield "Super, die Seite wurde erstellt."

    mock_vault = AsyncMock()
    mock_vault.retrieve = AsyncMock(return_value=json.dumps({"api_token": "tok"}))

    with (
        patch("app.services.input.get_llm_service") as mock_llm_factory,
        patch("app.services.input.get_mcp_client") as mock_mcp_factory,
        patch("app.services.input.settings") as mock_cfg,
    ):
        mock_cfg.mcp_enabled = True

        mock_llm = MagicMock()
        mock_llm.stream_response = _fake_stream
        mock_llm.model_name = "test-model"
        mock_llm._build_messages = MagicMock(
            return_value=[{"role": "user", "content": "T"}]
        )
        mock_llm.complete_with_tools = AsyncMock(
            side_effect=[
                LLMResponse(text=None, tool_calls=[tool_call]),  # first: tool call
                LLMResponse(text="Fertig", tool_calls=[]),  # second: text
            ]
        )
        mock_llm.build_assistant_tool_use_message = MagicMock(
            return_value={"role": "assistant", "content": []}
        )
        mock_llm.build_tool_result_message = MagicMock(
            return_value={"role": "user", "content": []}
        )
        mock_llm_factory.return_value = mock_llm

        mock_mcp = AsyncMock()
        mock_mcp.list_tools = AsyncMock(
            return_value=[
                MagicMock(
                    name="create_page",
                    description="Erstelle eine Seite",
                    inputSchema=MagicMock(model_dump=MagicMock(return_value={})),
                )
            ]
        )
        mock_mcp.call_tool = AsyncMock(return_value=mcp_result)
        mock_mcp_factory.return_value = mock_mcp

        events = await _collect_events(
            process_input_stream(db_session, _USER_A, "Neue Notiz", vault=mock_vault)
        )

    types = [e["type"] for e in events]
    assert "tool_call" in types

    tool_call_event = next(e for e in events if e["type"] == "tool_call")
    assert tool_call_event["service"] == "notion"
    assert tool_call_event["tool"] == "create_page"

    assert "done" in types


@pytest.mark.asyncio
async def test_process_input_stream_tool_result_updates_record_fields(
    db_session: AsyncSession,
) -> None:
    """After a successful tool call, tool and deep_link fields are persisted."""
    from app.services.llm.base import LLMResponse, ToolCall
    from app.services.mcp.client import ToolCallResult

    tool_call = ToolCall(
        id="tc_2", name="todoist__create_task", arguments={"content": "X"}
    )
    mcp_result = ToolCallResult(
        tool_name="create_task",
        service=ApplicationService.todoist,
        content=[
            {
                "type": "text",
                "text": "Aufgabe erstellt\ndeep_link: https://todoist.com/app/task/1",
            }
        ],
        is_error=False,
        deep_link="https://todoist.com/app/task/1",
    )

    async def _fake_stream(*args, **kwargs):
        yield "Erledigt."

    mock_vault = AsyncMock()
    mock_vault.retrieve = AsyncMock(return_value=json.dumps({"api_token": "tok"}))

    with (
        patch("app.services.input.get_llm_service") as mock_llm_factory,
        patch("app.services.input.get_mcp_client") as mock_mcp_factory,
        patch("app.services.input.settings") as mock_cfg,
    ):
        mock_cfg.mcp_enabled = True

        mock_llm = MagicMock()
        mock_llm.stream_response = _fake_stream
        mock_llm.model_name = "test-model"
        mock_llm._build_messages = MagicMock(
            return_value=[{"role": "user", "content": "X"}]
        )
        mock_llm.complete_with_tools = AsyncMock(
            side_effect=[
                LLMResponse(text=None, tool_calls=[tool_call]),
                LLMResponse(text="Erledigt.", tool_calls=[]),
            ]
        )
        mock_llm.build_assistant_tool_use_message = MagicMock(
            return_value={"role": "assistant", "content": []}
        )
        mock_llm.build_tool_result_message = MagicMock(
            return_value={"role": "user", "content": []}
        )
        mock_llm_factory.return_value = mock_llm

        mock_mcp = AsyncMock()
        mock_mcp.list_tools = AsyncMock(
            return_value=[
                MagicMock(
                    name="create_task",
                    description="Erstelle eine Aufgabe",
                    inputSchema=MagicMock(model_dump=MagicMock(return_value={})),
                )
            ]
        )
        mock_mcp.call_tool = AsyncMock(return_value=mcp_result)
        mock_mcp_factory.return_value = mock_mcp

        events = await _collect_events(
            process_input_stream(
                db_session, _USER_A, "Aufgabe hinzufügen", vault=mock_vault
            )
        )

    done_event = next(e for e in events if e["type"] == "done")
    input_id = uuid.UUID(str(done_event["input_id"]))

    result = await db_session.execute(select(UserInput).where(UserInput.id == input_id))
    record = result.scalar_one()
    assert record.tool == "todoist/create_task"
    assert record.deep_link == "https://todoist.com/app/task/1"


@pytest.mark.asyncio
async def test_process_input_stream_max_iterations_guard(
    db_session: AsyncSession,
) -> None:
    """Loop must stop after MAX_TOOL_ITERATIONS even if LLM keeps requesting tools."""
    from app.services.llm.base import LLMResponse, ToolCall
    from app.services.mcp.client import ToolCallResult

    tool_call = ToolCall(id="tc_loop", name="notion__create_page", arguments={})
    mcp_result = ToolCallResult(
        tool_name="create_page",
        service=ApplicationService.notion,
        content=[],
        is_error=False,
    )

    async def _fake_stream(*args, **kwargs):
        yield "Fallback."

    mock_vault = AsyncMock()
    mock_vault.retrieve = AsyncMock(return_value=json.dumps({"api_token": "tok"}))

    with (
        patch("app.services.input.get_llm_service") as mock_llm_factory,
        patch("app.services.input.get_mcp_client") as mock_mcp_factory,
        patch("app.services.input.settings") as mock_cfg,
        patch("app.services.input._MAX_TOOL_ITERATIONS", 2),
    ):
        mock_cfg.mcp_enabled = True

        mock_llm = MagicMock()
        mock_llm.stream_response = _fake_stream
        mock_llm.model_name = "test-model"
        mock_llm._build_messages = MagicMock(
            return_value=[{"role": "user", "content": "T"}]
        )
        # Always return a tool call — should be stopped by MAX_TOOL_ITERATIONS
        mock_llm.complete_with_tools = AsyncMock(
            return_value=LLMResponse(text=None, tool_calls=[tool_call])
        )
        mock_llm.build_assistant_tool_use_message = MagicMock(return_value={})
        mock_llm.build_tool_result_message = MagicMock(return_value={})
        mock_llm_factory.return_value = mock_llm

        mock_mcp = AsyncMock()
        mock_mcp.list_tools = AsyncMock(
            return_value=[
                MagicMock(
                    name="create_page",
                    description="Erstelle Seite",
                    inputSchema=MagicMock(model_dump=MagicMock(return_value={})),
                )
            ]
        )
        mock_mcp.call_tool = AsyncMock(return_value=mcp_result)
        mock_mcp_factory.return_value = mock_mcp

        events = await _collect_events(
            process_input_stream(db_session, _USER_A, "Loop-Test", vault=mock_vault)
        )

    # Must complete without infinite loop and reach "done"
    assert any(e["type"] == "done" for e in events)
    # call_tool was called exactly MAX_TOOL_ITERATIONS (2) times
    assert mock_mcp.call_tool.call_count == 2
