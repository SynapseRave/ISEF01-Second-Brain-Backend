---
name: test-endpoint
description: Generate a complete pytest test file for a FastAPI endpoint with happy path, auth failure, and validation tests.
disable-model-invocation: true
---

# Test Endpoint Generator

Generate a pytest test file for the specified endpoint following project conventions.

## Input

$ARGUMENTS should be a route file path (e.g., `app/api/routes/input.py`) or endpoint description.

## Steps

1. Read the route file to understand endpoints, request/response schemas, and dependencies
2. Read `tests/conftest.py` to understand available fixtures
3. Create a test file in the corresponding `tests/test_api/` directory

## Test File Template

```python
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


class TestCreateResource:
    """Tests for POST /api/resource"""

    async def test_success(self, authenticated_client: AsyncClient):
        """Valid request returns expected status and response."""
        response = await authenticated_client.post("/api/resource", json={...})
        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    async def test_unauthorized(self, client: AsyncClient):
        """No auth token returns 401."""
        response = await client.post("/api/resource", json={...})
        assert response.status_code == 401

    async def test_invalid_payload(self, authenticated_client: AsyncClient):
        """Invalid request body returns 422."""
        response = await authenticated_client.post("/api/resource", json={})
        assert response.status_code == 422
```

## Rules

- Use `pytest.mark.anyio` for async tests
- Group tests by endpoint in classes
- Descriptive test names: `test_<scenario>`
- Mock the service layer, not the database directly
- Each test class: happy path, 401 unauthorized, 422 validation
- DELETE endpoints: also test 404 not found
- GET with pagination: test default pagination, custom pagination, empty results
