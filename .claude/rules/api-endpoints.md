---
paths:
  - "app/api/**/*.py"
  - "tests/test_api/**/*.py"
---

# API Endpoint Patterns

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
    current_user: User = Depends(get_current_user),
) -> ResourceResponse:
    return await resource_service.create(db, current_user.id, payload)
```

## Error Handling

- Use `HTTPException` with specific status codes (400, 401, 403, 404, 409, 422)
- Always provide a `detail` message
- Let FastAPI/Pydantic handle 422 validation errors automatically
- Auth failures: 401 (invalid token) or 403 (insufficient permissions)

## Streaming Endpoints

For LLM streaming responses (POST /api/input):

```python
from fastapi.responses import StreamingResponse

@router.post("/api/input")
async def process_input(...) -> StreamingResponse:
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
    )
```

## Testing Requirements

Every route needs at minimum:
- One happy-path test (correct status code + response body)
- One auth-failure test (401 without token)
- One validation test (422 with invalid payload)
- For DELETE: also test 404 not found
- For GET with pagination: test default, custom, and empty results
