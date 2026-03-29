---
paths:
  - "app/api/**/*.py"
  - "tests/test_api/**/*.py"
---

# API Endpoint Patterns

## Conventions

- Base path: `/api`
- Response format: Pydantic models (auto-serialized by FastAPI)
- Error format: `{"detail": "message"}` with appropriate HTTP status
- Streaming: `StreamingResponse` with `text/event-stream` media type
- All errors caught and returned as user-friendly messages to the client

## Route Structure

Every route file in `app/api/routes/` must:

1. Create an `APIRouter` with a prefix and tag
2. Use Pydantic schemas from `app/schemas/` (never inline)
3. Use `Depends()` for auth (`get_current_user`) and DB session (`get_db`)
4. Call service layer for business logic
5. Return Pydantic response models, never raw dicts or ORM objects

## Standard Endpoint Signature

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/resource", tags=["resource"])

@router.post("/", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> ResourceResponse:
    return await resource_service.create(db, current_user, payload)
```

## Error Handling

- Use `HTTPException` with specific status codes (400, 401, 403, 404, 409, 422)
- Always provide a `detail` message
- Let FastAPI/Pydantic handle 422 validation errors automatically

## Streaming Endpoints

```python
from fastapi.responses import StreamingResponse

@router.post("/")
async def process_input(...) -> StreamingResponse:
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )
```

SSE event format:
```json
{"type": "status", "message": "..."}
{"type": "result", "data": {"response": "...", "deep_link": "..."}}
{"type": "done",   "input_id": 42}
{"type": "error",  "message": "..."}
```

## Testing Requirements

Every route needs at minimum:
- One happy-path test (correct status code + response body)
- One auth-failure test (401 without token)
- One validation test (422 with invalid payload)
- For DELETE: also test 404 not found
- For GET with pagination: test default, custom, and empty results

## Planned Endpoints

### `GET /health` — public, no auth
Simple alive check for K8s liveness probes and frontend.

### `/api/input`
- `POST /` — Process natural-language prompt, SSE stream, saves to history
- `GET /` — Paginated input history *(TODO)*
- `GET /{id}` — Single input detail incl. response *(TODO)*
- `DELETE /{id}` — Delete a single input *(TODO)*

### `/api/user`
- `GET /` — Keycloak profile + app settings
- `PUT /` — Update Keycloak profile (email, password) and/or app settings

### `/api/credential/ai`
- `POST /` — Store encrypted OpenAI / Anthropic API keys (BYOK)
- `PUT /` — Update existing keys
- `DELETE /` — Delete keys

### `/api/credential/applications`
- `POST /` — Store credentials for an external service (Notion, Todoist, Obsidian, OneNote, Google Calendar)
