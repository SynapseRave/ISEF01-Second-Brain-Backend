import json
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SecondBrainException
from app.db.models.user_input import UserInput


def _sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def save_input(db: AsyncSession, user_id: str, prompt: str) -> UserInput:
    """Persist a new UserInput record and return it with its generated id."""
    record = UserInput(user_id=user_id, prompt=prompt)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_input(db: AsyncSession, record: UserInput, **kwargs: object) -> None:
    """Update arbitrary fields on an existing UserInput record."""
    for key, value in kwargs.items():
        setattr(record, key, value)
    await db.commit()


async def process_input_stream(
    db: AsyncSession, user_id: str, prompt: str
) -> AsyncGenerator[str, None]:
    """Persist the prompt, stream progress events, and update the record on completion.

    Yields SSE-formatted strings. Each event carries a JSON payload with a
    ``type`` field: ``status``, ``result``, ``done``, or ``error``.
    """
    try:
        record = await save_input(db, user_id, prompt)

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

        yield _sse_event({"type": "done", "input_id": record.id})

    except SecondBrainException as exc:
        yield _sse_event({"type": "error", "message": exc.message})
    except Exception:
        yield _sse_event(
            {"type": "error", "message": "Ein unerwarteter Fehler ist aufgetreten."}
        )
