# Implementierungsplan: Initial Project Setup

Fokus: Grundlegendes Projekt-Setup, damit der Dev-Server laeuft, die DB angebunden ist,
Auth funktioniert und ein erster Endpunkt (Health) erreichbar ist.

**Scope**: Nur Setup — keine vollstaendige Feature-Implementierung.

---

## Phase 1: Python-Projekt anlegen

### 1.1 Projektstruktur erstellen
- [ ] Ordnerstruktur anlegen wie in CLAUDE.md definiert:
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
  │       ├── __init__.py
  │       └── auth.py
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
- [ ] `requirements.txt` erstellen mit:
  ```
  fastapi
  uvicorn[standard]
  sqlalchemy[asyncio]
  asyncpg
  alembic
  pydantic-settings
  python-jose[cryptography]
  httpx
  pytest
  pytest-asyncio
  httpx  # TestClient
  ruff
  ```

### 1.3 Ruff konfigurieren
- [ ] `pyproject.toml` mit ruff-Config (line-length=88, target Python 3.12)

### 1.4 Git-Konfiguration
- [ ] `.gitignore` fuer Python (venv, __pycache__, .env, *.pyc, .ruff_cache)
- [ ] `.env.example` mit allen benoetigten Variablen (ohne Werte)

---

## Phase 2: FastAPI App + Uvicorn Server

### 2.1 Config (pydantic-settings)
- [ ] `app/core/config.py` — Settings-Klasse mit:
  - `DATABASE_URL`
  - `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`
  - `CORS_ORIGINS` (fuer Frontend)
  - Laden aus `.env`

### 2.2 FastAPI App Entry
- [ ] `app/main.py`:
  - FastAPI-Instanz mit Lifespan (startup/shutdown)
  - CORS Middleware (Origins aus Config)
  - Exception Handler registrieren
  - Router einbinden

### 2.3 Health Endpunkt
- [ ] `app/api/routes/health.py`:
  - `GET /health` — gibt `{"status": "ok"}` zurueck
  - Kein Auth erforderlich

### 2.4 Custom Exceptions
- [ ] `app/core/exceptions.py`:
  - `SecondBrainException` Basisklasse
  - `NotFoundException`, `UnauthorizedException`
  - FastAPI Exception Handler registrieren

### 2.5 Ergebnis Phase 2
- Server startet mit `uvicorn app.main:app --reload --port 8000`
- `GET /health` antwortet mit 200

---

## Phase 3: PostgreSQL einbinden

### 3.1 Async Database Setup
- [ ] `app/db/database.py`:
  - `create_async_engine` mit `DATABASE_URL`
  - `async_sessionmaker` fuer `AsyncSession`
  - `get_db` Dependency (yields session)

### 3.2 Alembic einrichten
- [ ] `alembic init alembic` (async template)
- [ ] `alembic/env.py` anpassen:
  - `target_metadata` auf SQLAlchemy Base
  - Async Engine verwenden
- [ ] `alembic.ini` — `sqlalchemy.url` aus ENV

### 3.3 Erstes DB-Modell (Platzhalter)
- [ ] `app/db/models/user_input.py`:
  - `UserInput` Modell (id, user_id, prompt, response, created_at)
  - Dient als Grundlage fuer spaetere Input-Historie

### 3.4 Erste Migration
- [ ] `alembic revision --autogenerate -m "create user_input table"`
- [ ] Migration laeuft erfolgreich mit `alembic upgrade head`

### 3.5 DB Dependency
- [ ] `app/api/dependencies.py`:
  - `get_db` als FastAPI Dependency

---

## Phase 4: Keycloak Auth Middleware

### 4.1 Security Module
- [ ] `app/core/security.py`:
  - Keycloak Public Key abrufen (JWKS Endpoint)
  - JWT Validierung (Signatur, Ablauf, Issuer)
  - `decode_token()` Funktion

### 4.2 Auth Dependency
- [ ] `app/api/dependencies.py`:
  - `get_current_user` Dependency:
    - Liest `Authorization: Bearer <token>` Header
    - Validiert JWT via `security.py`
    - Gibt User-ID (`sub` claim) zurueck
    - Wirft 401 bei ungueltigem/fehlendem Token

### 4.3 Auth Middleware (optional, falls global)
- [ ] `app/api/middleware/auth.py`:
  - Middleware die `/health` ausschliesst
  - Alle anderen Routes erfordern validen JWT

---

## Phase 5: Test-Infrastruktur

### 5.1 Test-Setup
- [ ] `tests/conftest.py`:
  - Test-DB (SQLite async oder separate Postgres Test-DB)
  - `AsyncClient` (httpx) fuer API-Tests
  - Auth-Mock: Fixture die JWT-Validierung ueberspringt
  - DB-Session Fixture mit Rollback nach jedem Test

### 5.2 Erster Test
- [ ] `tests/test_api/test_health.py`:
  - Test: `GET /health` gibt 200 + `{"status": "ok"}`
  - Test: Geschuetzter Endpunkt ohne Token gibt 401

### 5.3 Pytest Config
- [ ] `pyproject.toml` pytest-Section:
  - `asyncio_mode = "auto"`
  - Test-Pfade

---

## Phase 6: Dockerfile

### 6.1 Dockerfile
- [ ] `Dockerfile`:
  - Python 3.12 slim Base Image
  - `requirements.txt` installieren
  - App kopieren
  - Uvicorn als Entrypoint
- [ ] `.dockerignore` (venv, .git, __pycache__, .env, tests)

---

## Zusammenfassung: Was nach dem Setup steht

| Komponente              | Status nach Setup                     |
|-------------------------|---------------------------------------|
| Projektstruktur         | Vollstaendig angelegt                 |
| FastAPI + Uvicorn       | Server laeuft, Health-Endpunkt aktiv  |
| PostgreSQL + SQLAlchemy | Async Engine, Session, erste Migration|
| Alembic                 | Konfiguriert, erste Migration erstellt|
| Keycloak Auth           | JWT-Validierung, Auth Dependency      |
| Tests                   | Infrastruktur + erster Health-Test    |
| Dockerfile              | Build-faehig                          |
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
