from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class SecondBrainException(Exception):
    """Base exception for the application."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(SecondBrainException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class UnauthorizedException(SecondBrainException):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, status_code=401)


async def second_brain_exception_handler(
    request: Request, exc: SecondBrainException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
