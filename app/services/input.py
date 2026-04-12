import json
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, SecondBrainException
from app.db.models.user_input import UserInput
from app.schemas.credential import ApplicationService
from app.services.llm import get_llm_service
from app.services.llm.base import MessageDict, ToolCall
from app.services.mcp import get_mcp_client
from app.services.mcp.client import ToolCallResult
from app.services.mcp.credentials import get_user_credentials_for_services
from app.services.vault.base import VaultService

_ALL_SERVICES = list(ApplicationService)
_MAX_TOOL_ITERATIONS = 3


def _sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def save_input(
    db: AsyncSession,
    user_id: str,
    prompt: str,
    conversation_id: uuid.UUID | None = None,
) -> UserInput:
    """Persist a new UserInput record and return it with its generated id.

    If no conversation_id is provided, a new UUID is generated so that every
    input belongs to a traceable conversation thread.
    """
    cid = conversation_id if conversation_id is not None else uuid.uuid4()
    record = UserInput(user_id=user_id, prompt=prompt, conversation_id=cid)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_input(db: AsyncSession, record: UserInput, **kwargs: object) -> None:
    """Update arbitrary fields on an existing UserInput record."""
    for key, value in kwargs.items():
        setattr(record, key, value)
    await db.commit()


async def get_inputs(
    db: AsyncSession, user_id: str, page: int, page_size: int
) -> tuple[list[UserInput], int]:
    """Return a paginated list of inputs for the given user, newest first.

    Returns a tuple of (records, total_count).
    """
    offset = (page - 1) * page_size

    records_result = await db.execute(
        select(UserInput)
        .where(UserInput.user_id == user_id)
        .order_by(UserInput.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    records = list(records_result.scalars().all())

    count_result = await db.execute(
        select(func.count()).select_from(UserInput).where(UserInput.user_id == user_id)
    )
    total = count_result.scalar_one()

    return records, total


async def get_input_by_id(db: AsyncSession, user_id: str, input_id: int) -> UserInput:
    """Return a single UserInput owned by the given user.

    Raises NotFoundException if the record does not exist or belongs to
    a different user.
    """
    result = await db.execute(
        select(UserInput).where(UserInput.id == input_id, UserInput.user_id == user_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise NotFoundException("Input nicht gefunden.")
    return record


async def delete_input(db: AsyncSession, user_id: str, input_id: int) -> None:
    """Delete a single UserInput owned by the given user.

    Raises NotFoundException if the record does not exist or belongs to
    a different user. Other messages in the same conversation are not affected.
    """
    record = await get_input_by_id(db, user_id, input_id)
    await db.delete(record)
    await db.commit()


async def get_conversation(
    db: AsyncSession, user_id: str, conversation_id: uuid.UUID
) -> list[UserInput]:
    """Return all messages in a conversation thread, ordered by creation time.

    Returns an empty list if no matching records are found.
    """
    result = await db.execute(
        select(UserInput)
        .where(
            UserInput.conversation_id == conversation_id,
            UserInput.user_id == user_id,
        )
        .order_by(UserInput.created_at.asc())
    )
    return list(result.scalars().all())


async def process_input_stream(
    db: AsyncSession,
    user_id: str,
    prompt: str,
    conversation_id: uuid.UUID | None = None,
    vault: VaultService | None = None,
) -> AsyncGenerator[str, None]:
    """Persist the prompt, stream progress events, and update the record on completion.

    When a vault is provided and MCP is enabled, available tool definitions are
    fetched from configured MCP servers and offered to the LLM. If the LLM
    requests a tool call it is executed and the result is fed back for up to
    ``_MAX_TOOL_ITERATIONS`` rounds before the final text is streamed.

    Yields SSE-formatted strings. Each event carries a JSON payload with a
    ``type`` field: ``status``, ``chunk``, ``tool_call``, ``result``, ``done``,
    or ``error``.
    """
    try:
        record = await save_input(db, user_id, prompt, conversation_id)

        yield _sse_event({"type": "status", "message": "Prompt wird analysiert..."})

        all_msgs = await get_conversation(db, user_id, record.conversation_id)
        history = [m for m in all_msgs if m.id != record.id]

        llm = get_llm_service()

        # --- Phase 1: collect tool definitions from configured MCP servers ---
        tool_definitions: list[dict] = []
        service_credentials: dict[ApplicationService, dict] = {}

        if vault is not None and settings.mcp_enabled:
            yield _sse_event(
                {"type": "status", "message": "Verbundene Dienste werden geprüft..."}
            )
            mcp = get_mcp_client()
            service_credentials = await get_user_credentials_for_services(
                user_id, _ALL_SERVICES, vault
            )
            for service, credentials in service_credentials.items():
                try:
                    tools = await mcp.list_tools(service, credentials)
                    for tool in tools:
                        tool_definitions.append(
                            {
                                "name": f"{service.value}__{tool.name}",
                                "description": tool.description or "",
                                "input_schema": (
                                    tool.inputSchema.model_dump()
                                    if tool.inputSchema
                                    else {}
                                ),
                            }
                        )
                except SecondBrainException:
                    pass  # MCP server unreachable — continue without it

        # --- Phase 2: agentic tool-use loop ---
        messages: list[MessageDict] = llm._build_messages(history, prompt)
        tool_used: str | None = None
        deep_link: str | None = None
        pre_streamed_text: str | None = None

        if tool_definitions:
            yield _sse_event({"type": "status", "message": "LLM wird angefragt..."})

            for _ in range(_MAX_TOOL_ITERATIONS):
                llm_response = await llm.complete_with_tools(messages, tool_definitions)

                if not llm_response.tool_calls:
                    # LLM decided no tool is needed
                    pre_streamed_text = llm_response.text
                    break

                # Execute each tool call and append the exchange to messages
                for tool_call in llm_response.tool_calls:
                    service_name, bare_tool_name = tool_call.name.split("__", 1)
                    service = ApplicationService(service_name)
                    credentials = service_credentials.get(service, {})

                    yield _sse_event(
                        {
                            "type": "tool_call",
                            "tool": bare_tool_name,
                            "service": service_name,
                        }
                    )

                    result = await get_mcp_client().call_tool(
                        service, bare_tool_name, tool_call.arguments, credentials
                    )

                    tool_used = f"{service_name}/{bare_tool_name}"
                    if result.deep_link:
                        deep_link = result.deep_link

                    messages = _append_tool_exchange(llm, messages, tool_call, result)
            # If all iterations consumed, fall through to final stream_response

        # --- Phase 3: stream the final text response ---
        yield _sse_event({"type": "status", "message": "Antwort wird generiert..."})

        chunks: list[str] = []
        if pre_streamed_text is not None:
            chunks = [pre_streamed_text]
            yield _sse_event({"type": "chunk", "text": pre_streamed_text})
        else:
            # Pass enriched messages when tools were used, otherwise plain history
            override = messages if tool_definitions else None
            async for token in llm.stream_response(history, prompt, messages=override):
                chunks.append(token)
                yield _sse_event({"type": "chunk", "text": token})

        response_text = "".join(chunks)
        model_used: str | None = llm.model_name

        yield _sse_event({"type": "status", "message": "Verarbeitung abgeschlossen."})
        yield _sse_event(
            {
                "type": "result",
                "data": {
                    "response": response_text,
                    "deep_link": deep_link,
                },
            }
        )

        await update_input(
            db,
            record,
            response=response_text,
            tool=tool_used,
            model=model_used,
            deep_link=deep_link,
        )

        yield _sse_event(
            {
                "type": "done",
                "input_id": record.id,
                "conversation_id": str(record.conversation_id),
            }
        )

    except SecondBrainException as exc:
        yield _sse_event({"type": "error", "message": exc.message})
    except Exception:
        yield _sse_event(
            {"type": "error", "message": "Ein unerwarteter Fehler ist aufgetreten."}
        )


def _append_tool_exchange(
    llm: object,
    messages: list[MessageDict],
    tool_call: ToolCall,
    result: ToolCallResult,
) -> list[MessageDict]:
    """Append the assistant tool-use message and tool result to the message list.

    Args:
        llm: The LLMService instance (provides provider-specific message builders).
        messages: Current message list.
        tool_call: The tool call the assistant made.
        result: The MCP tool execution result.

    Returns:
        New message list with the exchange appended.
    """
    from app.services.llm.base import LLMService

    assert isinstance(llm, LLMService)
    assistant_msg = llm.build_assistant_tool_use_message(tool_call)
    result_msg = llm.build_tool_result_message(
        tool_call, result.content, result.is_error
    )
    return [*messages, assistant_msg, result_msg]
