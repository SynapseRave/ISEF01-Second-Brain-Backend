from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token

EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Global JWT auth middleware.

    Validates the Bearer token for all routes except those in EXCLUDED_PATHS.
    Sets request.state.user_id on success so routes can read it if needed.
    CORS preflight (OPTIONS) requests are always passed through.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.method == "OPTIONS" or request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )

        token = auth_header.removeprefix("Bearer ")
        try:
            payload = await decode_token(token)
            request.state.user_id = payload["sub"]
        except UnauthorizedException as exc:
            return JSONResponse(
                status_code=401,
                content={"detail": exc.message},
            )

        return await call_next(request)
