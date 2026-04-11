# Architecture & Authentication

## Core Patterns

- **Service layer**: Routes → Services → DB/External APIs. No business logic in routes.
- **Abstract LLM class**: `app/services/llm/base.py` defines the interface. ChatGPT and Claude inherit from it. Never call SDKs directly from routes.
- **Async everywhere**: `async def` for all routes, services, and DB ops. Always use `AsyncSession`.
- **Dependency injection**: Use FastAPI `Depends()` for DB sessions, current user, and services.
- **Pydantic schemas**: Separate `Create`, `Update`, `Response` schemas. Never return ORM models from routes.
- **MCP client pattern**: One shared MCP client (`app/services/mcp/client.py`). External services (Notion, Todoist, etc.) are MCP servers — these are APPLICATION features, not Claude Code tooling.

## Authentication

- All endpoints except `GET /health` require a valid Keycloak JWT
- JWT is validated via Keycloak's public key in `app/api/middleware/auth.py`
- User identity comes from the JWT `sub` claim (`get_current_user` dependency)
- Never store passwords or Keycloak credentials in this backend
- Auth failures return 401 (invalid/missing token) or 403 (insufficient permissions)
