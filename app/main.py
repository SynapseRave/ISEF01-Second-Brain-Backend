from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.auth import AuthMiddleware
from app.api.routes import config, credential, health, input, user
from app.core.config import settings
from app.core.exceptions import (
    SecondBrainException,
    http_exception_handler,
    second_brain_exception_handler,
    unhandled_exception_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown logic."""
    yield


app = FastAPI(
    title="Second Brain API",
    description="Backend for the Second Brain unified productivity interface.",
    version="0.1.0",
    lifespan=lifespan,
    swagger_ui_init_oauth={
        "clientId": settings.keycloak_client_id,
        "realm": settings.keycloak_realm,
        "appName": "Second Brain API",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(SecondBrainException, second_brain_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(health.router)
app.include_router(user.router)
app.include_router(input.router)
app.include_router(credential.router)
app.include_router(config.router)
