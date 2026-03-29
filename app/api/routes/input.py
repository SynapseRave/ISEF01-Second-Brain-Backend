from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.schemas.input import InputRequest
from app.services.input import process_input_stream

router = APIRouter(prefix="/api/input", tags=["input"])


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
    """
    return StreamingResponse(
        process_input_stream(db, user_id, body.prompt),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/")
async def list_inputs(
    user_id: str = Depends(get_current_user),
) -> dict:
    """Return paginated history of user inputs. (TODO)"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Noch nicht implementiert.",
    )


@router.get("/{input_id}")
async def get_input(
    input_id: int,
    user_id: str = Depends(get_current_user),
) -> dict:
    """Return detail view of a single input including its response. (TODO)"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Noch nicht implementiert.",
    )


@router.delete("/{input_id}")
async def delete_input(
    input_id: int,
    user_id: str = Depends(get_current_user),
) -> dict:
    """Delete a single user input by id. (TODO)"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Noch nicht implementiert.",
    )
