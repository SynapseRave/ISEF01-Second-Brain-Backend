# Architecture & Authentication

## Core Patterns

- **Service layer**: Routes → Services → DB/External APIs. No business logic in routes.
- **Abstract LLM class**: `app/services/llm/base.py` defines the interface. ChatGPT and Claude inherit from it. Never call SDKs directly from routes.
- **Async everywhere**: `async def` for all routes, services, and DB ops. Always use `AsyncSession`.
- **Dependency injection**: Use FastAPI `Depends()` for DB sessions, current user, and services.
- **Pydantic schemas**: Separate `Create`, `Update`, `Response` schemas. Never return ORM models from routes.
- **MCP client pattern**: One shared MCP client (`app/services/mcp/client.py`). External services (Notion, Todoist, etc.) are MCP servers — these are APPLICATION features, not Claude Code tooling.

## Vault / Credential Storage

User credentials for external services (Notion, Todoist, Obsidian, Google Calendar, OneNote) are stored encrypted via the `VaultService` abstraction in `app/services/vault/`.

**Pattern** (mirrors the LLM abstraction):
- `base.py` — abstract interface: `store(path, value)`, `retrieve(path)`, `delete(path)`
- `local.py` — `LocalVaultService`: Fernet-encrypted rows in the `credentials` table (default for dev)
- `hashicorp.py` — `HashiCorpVaultService`: placeholder stub
- `__init__.py` — factory function `get_vault_service(db)` driven by `VAULT_BACKEND` env var

**Path format**: `"{user_id}/{service}"` — maps cleanly to HashiCorp Vault KV paths.

**To add a new vault backend:**
1. Create `app/services/vault/<name>.py` implementing `VaultService` (`store`, `retrieve`, `delete`)
2. Add the new case to the factory in `app/services/vault/__init__.py`
3. Add any required settings to `app/core/config.py` (e.g. `vault_url`, `vault_token`)
4. Add the Python client library to `requirements.txt`
5. No changes needed anywhere else (routes, credential service, schemas)

**Rules:**
- Never return decrypted credentials in API responses
- Never log credential values
- Routes inject `VaultService` via `Depends(_get_vault)` in `app/api/routes/credential.py`
- Business logic lives in `app/services/credential.py`, not in routes

## Authentication

- All endpoints except `GET /health` require a valid Keycloak JWT
- JWT is validated via Keycloak's public key in `app/api/middleware/auth.py`
- User identity comes from the JWT `sub` claim (`get_current_user` dependency)
- Never store passwords or Keycloak credentials in this backend
- Auth failures return 401 (invalid/missing token) or 403 (insufficient permissions)
