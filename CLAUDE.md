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
