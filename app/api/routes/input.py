import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.schemas.input import (
    ConversationResponse,
    InputRequest,
    InputResponse,
    PaginatedInputResponse,
)
from app.services.input import (
    delete_input,
    get_conversation,
    get_input_by_id,
    get_inputs,
    process_input_stream,
)

router = APIRouter(prefix="/api/input", tags=["input"])


@router.get("/", response_model=PaginatedInputResponse)
async def list_inputs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedInputResponse:
    """Return a paginated history of all inputs for the current user, newest first."""
    records, total = await get_inputs(db, user_id, page, page_size)
    pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedInputResponse(
        items=[InputResponse.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_thread(
    conversation_id: uuid.UUID,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConversationResponse:
    """Return all messages in a conversation thread ordered by creation time."""
    messages = await get_conversation(db, user_id, conversation_id)
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Konversation nicht gefunden.",
        )
    return ConversationResponse(
        conversation_id=conversation_id,
        messages=[InputResponse.model_validate(m) for m in messages],
        total=len(messages),
    )


@router.get("/{input_id}", response_model=InputResponse)
async def get_input(
    input_id: int,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> InputResponse:
    """Return detail view of a single input including its response."""
    record = await get_input_by_id(db, user_id, input_id)
    return InputResponse.model_validate(record)


@router.post("/")
async def post_input(
    body: InputRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """Process a natural-language user command and stream progress as SSE.

    Each streamed event is a JSON object on a ``data:`` line with a ``type``
    field (``status``, ``result``, ``done``, or ``error``).
    The prompt is persisted to the database for history retrieval.
    Provide ``conversation_id`` to append to an existing thread.
    """
    return StreamingResponse(
        process_input_stream(db, user_id, body.prompt, body.conversation_id),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.delete("/{input_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_input_route(
    input_id: int,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a single input by id. Only the owner may delete their own inputs."""
    await delete_input(db, user_id, input_id)
