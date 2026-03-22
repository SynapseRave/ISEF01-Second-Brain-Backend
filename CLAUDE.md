# Second Brain - Multi-App Interface (Backend)

University project (ISEF01) — Backend API for a unified productivity interface.
Connects to external services (Notion, Todoist, Obsidian, OneNote, Google Calendar)
via MCP infrastructure and provides LLM-powered input processing.

## Tech Stack
- **Language**: Python 3.12
- **Framework**: FastAPI
- **Database**: PostgreSQL via SQLAlchemy (async) + Alembic migrations
- **Server**: Uvicorn (ASGI)
- **Auth**: Keycloak (OIDC / JWT validation)
- **External Services**: MCP (Model Context Protocol) for Notion, Todoist, Obsidian, OneNote, Google Calendar
- **LLM**: OpenAI (ChatGPT) + Anthropic (Claude) APIs
- **Streaming**: SSE (Server-Sent Events) via StreamingResponse

## Project Structure
```
app/
├── main.py                  # FastAPI app entry, middleware, lifespan
├── api/
│   ├── routes/              # Route handlers (one file per resource)
│   ├── dependencies.py      # Shared deps (auth, db session)
│   └── middleware/           # Auth middleware (Keycloak JWT)
├── core/
│   ├── config.py            # Settings via pydantic-settings (.env)
│   ├── security.py          # JWT validation, Keycloak integration
│   └── exceptions.py        # Custom exceptions + handlers
├── db/
│   ├── database.py          # Async engine + session factory
│   └── models/              # SQLAlchemy ORM models
├── schemas/                 # Pydantic request/response schemas
├── services/                # Business logic layer
│   ├── llm/
│   │   ├── base.py          # Abstract LLM base class
│   │   ├── chatgpt.py       # OpenAI implementation
│   │   └── claude.py        # Anthropic implementation
│   └── mcp/
│       ├── client.py        # MCP client
│       └── servers/         # MCP server configs per service
├── tests/
│   ├── conftest.py          # Fixtures (test DB, client, auth mock)
│   ├── test_api/            # Route tests
│   └── test_services/       # Service/unit tests
└── alembic/
    ├── env.py
    └── versions/            # Migration files
```

## Commands
```bash
uvicorn app.main:app --reload --port 8000   # Dev server
pytest                                       # All tests
pytest tests/test_api/ -x -v                 # API tests, stop on first failure
alembic upgrade head                         # Apply migrations
alembic revision --autogenerate -m "desc"    # Create migration
alembic downgrade -1                         # Rollback last migration
ruff check . --fix                           # Lint + auto-fix
ruff format .                                # Format
pip install -r requirements.txt              # Install deps
```

## Architecture Decisions
- **Service layer pattern**: Routes -> Services -> DB/External APIs. No business logic in routes.
- **Abstract LLM class**: `app/services/llm/base.py` defines the interface. ChatGPT and Claude inherit from it. Never call SDKs directly from routes.
- **Async everywhere**: async def for routes, services, DB ops. Use `AsyncSession`.
- **Dependency injection**: Use FastAPI `Depends()` for DB sessions, current user, services.
- **Pydantic schemas**: Separate Create, Update, Response schemas. Never return ORM models from routes.
- **MCP client pattern**: One MCP client (`app/services/mcp/client.py`). External services are MCP servers.

## Authentication
- All endpoints except `GET /health` require a valid Keycloak JWT
- JWT validated via Keycloak's public key in auth middleware
- User identity from JWT `sub` claim
- Never store passwords or Keycloak credentials in this backend

## API Endpoints (from requirements)

### Health — `GET /health`
Einfacher Alive-Check ohne Auth. Wird von K8s Liveness-Probes und dem Frontend genutzt.

### User Input — `/api/input`
Kernfunktion der App: Der User gibt im Frontend einen natuerlichsprachlichen Befehl ein
(z.B. "Erstelle eine Notiz zu meinem Meeting morgen" oder "Fuege Milch zur Einkaufsliste hinzu").
Das Backend verarbeitet diesen Input ueber den LLM-Service, der entscheidet welche
externen Dienste (Notion, Todoist, etc.) via MCP angesprochen werden.

- `POST /api/input` — Verarbeitet den User-Prompt. Streaming-Antwort (SSE), damit das
  Frontend den Verarbeitungsfortschritt live anzeigen kann (welcher Dienst wird gerade
  angesprochen, was passiert). Nach Abschluss: Deep Link / External Link zum erstellten
  Objekt im Zielsystem. Der Prompt wird fuer die Historie gespeichert.
- `GET /api/input` — Paginierte Historie aller bisherigen Eingaben des Users (Parameter tbd).
- `GET /api/input/:id` — Detailansicht eines einzelnen Inputs inkl. Antwort.
- `DELETE /api/input` — Loescht einen einzelnen Input anhand seiner ID.

### User Settings — `/api/user`
Benutzerprofil-Verwaltung. Das Backend speichert keine eigenen User-Daten, sondern
proxied Anfragen direkt an Keycloak (Profildaten wie Name, E-Mail kommen aus dem
Keycloak-Realm). Zusaetzlich koennen benutzerspezifische Einstellungen der App hier
verwaltet werden (z.B. bevorzugter LLM-Provider, Standard-Zielsystem pro Eingabetyp).

- `GET /api/user` — Liest Profildaten aus Keycloak + App-spezifische Einstellungen.
- `PUT /api/user` — Aktualisiert Profil (Keycloak-Proxy) und/oder App-Einstellungen.

### AI Credentials — `/api/credential/ai`
User bringen ihre eigenen API-Keys fuer ChatGPT und Claude mit (BYOK-Modell).
Die Keys werden verschluesselt in der DB gespeichert (Encryption-at-Rest, Ansatz tbd)
und nur zur Laufzeit entschluesselt, wenn der LLM-Service sie braucht.

- `POST /api/credential/ai` — Speichert API-Keys (ChatGPT und/oder Claude).
- `PUT /api/credential/ai` — Aktualisiert bestehende API-Keys.
- `DELETE /api/credential/ai` — Loescht API-Keys des Users.

### External Application Keys — `/api/credential/applications`
Zugangsdaten fuer die externen Dienste, die via MCP angebunden werden.
Pro Dienst (Notion, Todoist, Obsidian, OneNote, Google Calendar) wird ein eigener
Credential-Eintrag verwaltet. Die Einstellungsseite im Frontend zeigt den
Verbindungsstatus je Dienst (connected/disconnected/error).

- `POST /api/credential/applications` — Speichert Credentials fuer einen externen Dienst.
- Jeweils ein Eintrag pro Dienst: Notion, Todoist, Obsidian, OneNote, Google Calendar.

## API Conventions
- Base path: `/api`
- Response format: Pydantic models (auto-serialized by FastAPI)
- Error format: `{"detail": "message"}` with appropriate HTTP status
- Streaming: `StreamingResponse` with `text/event-stream` media type
- All errors caught and returned as user-friendly messages to the client

## Code Style
- PEP 8, enforced by ruff
- Type hints on all function signatures
- Google-style docstrings on public functions/classes
- `snake_case` for variables/functions, `PascalCase` for classes
- Max line length: 88 (ruff default)
- Limited function code length (max. 50 lines)
- Use helper functions to split complex structure

## Environment Variables
- All config via `.env`, loaded by `pydantic-settings`
- NEVER hardcode secrets, API keys, or DB credentials
- NEVER commit `.env` to git
- Required: `DATABASE_URL`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`

## Git Branching Strategy
- `main` — heiliger Branch, nur fuer Deployments. Kein direkter Commit. Merge nur aus `develop`.
- `develop` — Basis-Branch fuer die Entwicklung. Feature-/Bugfix-Branches werden hier gemergt.
- `feature/<name>` — Implementierung neuer Features (von `develop` abzweigen, in `develop` mergen).
- `bugfix/<name>` — Bugfixes (von `develop` abzweigen, in `develop` mergen).

**Flow**: `feature/` oder `bugfix/` → Pull Request → `develop` → Pull Request → `main`

**Regeln**:
- Nie direkt auf `main` oder `develop` pushen
- Immer einen Pull Request erstellen (auch als Solo-Entwickler — fuer Nachvollziehbarkeit)
- Feature-Branch pro Phase oder sinnvoller Einheit

## IMPORTANT
- This is a university project — keep solutions pragmatic, not over-engineered
- MCP servers here are APPLICATION features, not Claude Code tooling
- Always run tests after code changes
- Never commit directly to `main` or `develop` — always use feature/bugfix branches + PR
