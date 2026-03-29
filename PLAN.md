# Implementierungsplan: Initial Project Setup

Fokus: Grundlegendes Projekt-Setup, damit der Dev-Server laeuft, die DB angebunden ist,
Auth funktioniert und ein erster Endpunkt (Health) erreichbar ist.

**Scope**: Nur Setup — keine vollstaendige Feature-Implementierung.

---

## Phase 1: Initial Setup (vollstaendig)

### 1.1 Projektstruktur erstellen
- [x] Ordnerstruktur anlegen wie in CLAUDE.md definiert:
  ```
  app/
  ├── __init__.py
  ├── main.py
  ├── api/
  │   ├── __init__.py
  │   ├── routes/
  │   │   ├── __init__.py
  │   │   └── health.py
  │   ├── dependencies.py
  │   └── middleware/
  │       └── __init__.py
  ├── core/
  │   ├── __init__.py
  │   ├── config.py
  │   ├── security.py
  │   └── exceptions.py
  ├── db/
  │   ├── __init__.py
  │   ├── database.py
  │   └── models/
  │       └── __init__.py
  ├── schemas/
  │   └── __init__.py
  ├── services/
  │   ├── __init__.py
  │   ├── llm/
  │   │   └── __init__.py
  │   └── mcp/
  │       ├── __init__.py
  │       └── servers/
  │           └── __init__.py
  └── tests/
      ├── __init__.py
      ├── conftest.py
      ├── test_api/
      │   └── __init__.py
      └── test_services/
          └── __init__.py
  ```

### 1.2 Dependencies definieren
- [x] `requirements.txt` mit gepinnten Versionen:
  - `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`
  - `pydantic-settings`, `python-jose[cryptography]`, `httpx`
  - `pytest`, `pytest-asyncio`

### 1.3 Ruff konfigurieren
- [x] `pyproject.toml` mit ruff-Config (line-length=88, target Python 3.12, select E/F/I/UP)
- [x] `pyproject.toml` pytest-Section: `asyncio_mode = "auto"`, `testpaths = ["tests"]`

### 1.4 Git-Konfiguration
- [x] `.gitignore` fuer Python (venv, __pycache__, .env, *.pyc, .ruff_cache)
- [x] `.env.example` mit allen benoetigten Variablen inkl. Docker-Hinweisen

### 1.5 Docker Setup (lokale Entwicklung)
- [x] `docker-compose.yml`:
  - `postgres:17` (PostgreSQL LTS) mit persistentem Volume und Health-Check
  - `quay.io/keycloak/keycloak:26.0` im `start-dev` Modus (embedded H2)
  - `backend` Service mit Hot-Reload via Volume-Mount, `depends_on` Postgres
- [x] `Dockerfile`: Python 3.12 slim, `requirements.txt`, Uvicorn Entrypoint
- [x] `.dockerignore`: venv, .git, __pycache__, .env, tests

### 1.6 FastAPI App + Config
- [x] `app/core/config.py`: Settings via pydantic-settings (`DATABASE_URL`, `KEYCLOAK_*`, `CORS_ORIGINS`)
- [x] `app/main.py`: FastAPI-Instanz mit Lifespan, CORS Middleware, Exception Handler, Router
- [x] `app/api/routes/health.py`: `GET /health` — gibt `{"status": "ok"}` zurueck, kein Auth
- [x] `app/core/exceptions.py`: `SecondBrainException`, `NotFoundException`, `UnauthorizedException` + Handler

### 1.7 PostgreSQL + Alembic
- [x] `app/db/database.py`: `create_async_engine`, `async_sessionmaker`, `get_db` Dependency
- [x] `alembic/env.py`: async Engine, `target_metadata` auf SQLAlchemy Base
- [x] `alembic.ini`: `sqlalchemy.url` aus ENV
- [x] `app/db/models/user_input.py`: `UserInput` Modell (id, user_id, prompt, response, deep_link, created_at)
- [x] Migration `0001_create_user_input_table` erstellt

### 1.8 Keycloak Auth
- [x] `app/core/security.py`: Keycloak JWKS abrufen + cachen, JWT-Validierung (RS256), `decode_token()`
- [x] `app/api/dependencies.py`: `get_current_user` (liest Bearer Token, validiert via `decode_token`, gibt `sub` zurueck), `get_db_session`
- [ ] `app/api/middleware/auth.py` (optional, global): Middleware die `/health` ausschliesst — **noch nicht umgesetzt**

### 1.9 Test-Infrastruktur
- [x] `tests/conftest.py`: Env-Vars-Setup, `client` Fixture (AsyncClient), `authenticated_client` Fixture (JWT-Mock via `patch`)
- [x] `tests/test_api/test_health.py`: `GET /health` → 200 + `{"status": "ok"}`
- [ ] DB-Session Fixture mit Rollback nach jedem Test — **noch nicht umgesetzt**
- [ ] Test: Geschuetzter Endpunkt ohne Token gibt 401 — **noch nicht umgesetzt** (kein geschuetzter Endpunkt in Phase 1)

---

## Zusammenfassung: Was nach dem Setup steht

| Komponente              | Status                                |
|-------------------------|---------------------------------------|
| Projektstruktur         | Vollstaendig angelegt                 |
| FastAPI + Uvicorn       | Server laeuft, Health-Endpunkt aktiv  |
| PostgreSQL + SQLAlchemy | Async Engine, Session, erste Migration|
| Alembic                 | Konfiguriert, erste Migration erstellt|
| Keycloak Auth           | JWT-Validierung, Auth Dependency      |
| Tests                   | Infrastruktur + erster Health-Test    |
| Docker                  | Dockerfile + docker-compose           |
| Linting/Formatting      | ruff konfiguriert                     |

---

## Naechste Schritte (NICHT Teil dieses Plans)

Nach dem Setup folgen die Feature-Implementierungen gemaess Backlog:
1. **Datenbank-Modelle** modellieren (UserInput, Credentials, etc.)
2. **User Input Endpunkt** (POST /api/input) mit LLM-Anbindung + Streaming
3. **User Input Historie** (GET /api/input, GET /api/input/:id, DELETE /api/input)
4. **AI Credentials** CRUD (POST/UPDATE/DELETE /api/credential/ai)
5. **External App Keys** (POST /api/credential/applications)
6. **User Settings** (UPDATE /api/user)
7. **LLM Service Layer** (Abstract Base + ChatGPT + Claude Implementierung)
8. **MCP Infrastruktur** (Client + Server-Configs fuer Notion, Todoist, etc.)
