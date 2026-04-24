# Second Brain - Multi-App Interface (Backend)

University project (ISEF01) — FastAPI backend for a unified productivity interface.
Connects to Notion, Todoist, Obsidian, OneNote, Google Calendar via MCP and provides LLM-powered input processing.

## Tech Stack
- **Language**: Python 3.12 / **Framework**: FastAPI / **Server**: Uvicorn
- **Database**: PostgreSQL + SQLAlchemy (async) + Alembic
- **Auth**: Keycloak (OIDC / JWT)
- **External Services**: MCP (Notion, Todoist, Obsidian, OneNote, Google Calendar)
- **LLM**: OpenAI + Anthropic / **Streaming**: SSE via StreamingResponse

## Project Structure
```
app/
├── main.py                  # FastAPI app entry, middleware, lifespan
├── api/
│   ├── routes/              # Route handlers (one file per resource)
│   ├── dependencies.py      # Shared deps (auth, db session)
│   └── middleware/          # Auth middleware (Keycloak JWT)
├── core/
│   ├── config.py            # Settings via pydantic-settings (.env)
│   ├── security.py          # JWT validation, Keycloak integration
│   └── exceptions.py        # Custom exceptions + handlers
├── db/
│   ├── database.py          # Async engine + session factory
│   └── models/              # SQLAlchemy ORM models
├── schemas/                 # Pydantic request/response schemas
├── services/                # Business logic layer
│   ├── llm/                 # base.py + chatgpt.py + claude.py
│   └── mcp/                 # client.py + servers/
└── tests/
    ├── conftest.py
    ├── test_api/
    └── test_services/
```

## Commands
```bash
uvicorn app.main:app --reload --port 8000   # Dev server
pytest                                       # All tests
pytest tests/test_api/ -x -v                 # API tests
ruff check . --fix && ruff format .          # Lint + format
alembic upgrade head                         # Apply migrations
alembic revision --autogenerate -m "desc"    # Create migration
```

## Rules
Detailed conventions are in `.claude/rules/`:
- `architecture.md` — Service layer, async patterns, auth
- `api-endpoints.md` — Route structure, error handling, SSE, planned endpoints
- `database.md` — Models, migrations, schemas, credential storage
- `code-structure.md` — File layout, naming, style

## Git Branching
- `main` — deployments only, merge from `develop` via PR
- `develop` — base branch, merge feature/bugfix branches via PR
- `feature/<name>` / `bugfix/<name>` — branch from `develop`, PR back to `develop`

## IMPORTANT
- Never commit directly to `main` or `develop` — always PR
- After every implementation: `ruff check . --fix && ruff format .` then run tests
- After implementation create a pull request for the feature branch
- Always test new endpoints via test-endpoint skill
- Migrations: use `0001_initial.py` and reset DB after changes:
  `docker compose down && docker volume rm isef01_second_brain_backend_postgres_data && docker compose up -d`

## Current Implementation Status (2026-04-24)

**Done:**
- Keycloak OIDC middleware (JWT validation on all routes except `/health`)
- `POST /api/input/` — SSE streaming with agentic tool-use loop (max 3 iterations)
- `CRUD /api/credential/applications/` — encrypted via Fernet/Vault
- 5 MCP servers: notion (3001), todoist (3002), google_calendar (3003), obsidian (3004), onenote (3005)
- Credentials forwarded as `X-Service-Credentials` header to MCP servers
- Keycloak realm export: `frontend` public client with PKCE S256 and correct redirect URIs
- `keycloak/setup-users.sh`: sets test-user passwords via Admin API (Keycloak 26 workaround)

**Required .env variables:**
```
DATABASE_URL=postgresql+asyncpg://...
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=second-brain
KEYCLOAK_CLIENT_ID=frontend
KEYCLOAK_ADMIN_USER=admin
KEYCLOAK_ADMIN_PASSWORD=admin
VAULT_MASTER_KEY=<32-byte URL-safe base64 Fernet key>
LLM_PROVIDER=openai          # or: anthropic
OPENAI_API_KEY=sk-...        # if LLM_PROVIDER=openai
ANTHROPIC_API_KEY=sk-ant-... # if LLM_PROVIDER=anthropic
CORS_ORIGINS=["http://localhost:3000"]
```

## SSE Event Protocol

`POST /api/input/` emits these events in order:

| Type | Payload | Notes |
|---|---|---|
| `status` | `{"message": "..."}` | Intermediate status |
| `tool_call` | `{"tool": "...", "service": "..."}` | Tool being executed |
| `chunk` | `{"text": "..."}` | Single LLM token (many) |
| `result` | `{"data": {"response": "...", "deep_link": ...}}` | Full assembled response |
| `done` | `{"input_id": "<uuid>", "conversation_id": "<uuid>"}` | **input_id is a UUID string, not int** |
| `error` | `{"message": "..."}` | Error message |

## Credential Schemas

| Service | Fields |
|---|---|
| Notion | `api_token` |
| Todoist | `api_token` |
| Obsidian | `api_key`, `base_url` (default: `http://localhost:27123`) |
| Google Calendar | `access_token`, `refresh_token`, `expires_at` |
| OneNote | `access_token`, `refresh_token`, `expires_at` |
