from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint. No authentication required.

    Used by Kubernetes liveness probes and the frontend to verify the service is up.
    """
    return {"status": "ok"}
