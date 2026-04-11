import json
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, SecondBrainException
from app.db.models.user_input import UserInput


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
) -> AsyncGenerator[str, None]:
    """Persist the prompt, stream progress events, and update the record on completion.

    Yields SSE-formatted strings. Each event carries a JSON payload with a
    ``type`` field: ``status``, ``result``, ``done``, or ``error``.
    """
    try:
        record = await save_input(db, user_id, prompt, conversation_id)

        yield _sse_event({"type": "status", "message": "Prompt wird analysiert..."})
        yield _sse_event(
            {"type": "status", "message": "Identifiziere benötigte Services..."}
        )

        # TODO: LLM/MCP integration
        # intent = await llm_service.determine_intent(prompt, user_settings)
        # yield _sse_event({"type": "status", "message": f"Nutze {intent.tool}..."})
        # result = await mcp_client.call_tool(intent.tool, intent.params)
        # response_text = result.response
        # tool_used = intent.tool
        # model_used = intent.model
        # deep_link = result.deep_link

        response_text = (
            "Verarbeitung noch nicht implementiert — LLM/MCP Integration folgt."
        )
        tool_used: str | None = None
        model_used: str | None = None
        deep_link: str | None = None

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
