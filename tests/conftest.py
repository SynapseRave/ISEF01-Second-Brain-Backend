import os
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Provide required env vars before any app module is imported
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://secondbrain:secondbrain@localhost:5432/secondbrain",
)
os.environ.setdefault("KEYCLOAK_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "test-realm")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test-client")
os.environ.setdefault("KEYCLOAK_ADMIN_USER", "admin")
os.environ.setdefault("KEYCLOAK_ADMIN_PASSWORD", "admin")
os.environ.setdefault("LLM_PROVIDER", "openai")

from app.db.database import Base  # noqa: E402
from app.main import app  # noqa: E402

# Separate test DB so tests never touch the app database.
# Overridable via TEST_DATABASE_URL env var.
_APP_DB_URL = "postgresql+asyncpg://secondbrain:secondbrain@localhost:5432/secondbrain"
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://secondbrain:secondbrain@localhost:5432/secondbrain_test",
)


async def _ensure_test_db() -> None:
    """Create the secondbrain_test database if it does not exist yet.

    Connects to the app DB with AUTOCOMMIT (required for CREATE DATABASE).
    """
    engine = create_async_engine(_APP_DB_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = 'secondbrain_test'")
        )
        if not exists:
            await conn.execute(text("CREATE DATABASE secondbrain_test"))
    await engine.dispose()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client for the FastAPI app.

    Auth is mocked out — use `authenticated_client` for protected routes.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL session against secondbrain_test, rolled back after each test.

    Creates the test DB and tables automatically on first use.
    Tables are dropped after each test to guarantee a clean slate.
    """
    await _ensure_test_db()

    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def authenticated_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with Keycloak JWT validation bypassed.

    Injects a fixed user_id ("test-user-123") as the current user.
    """
    with (
        patch(
            "app.api.middleware.auth.decode_token",
            return_value={"sub": "test-user-123"},
        ),
        patch(
            "app.api.dependencies.decode_token",
            return_value={"sub": "test-user-123"},
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as ac:
            yield ac
