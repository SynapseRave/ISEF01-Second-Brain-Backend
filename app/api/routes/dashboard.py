from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_vault
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import fetch_dashboard_data
from app.services.vault.base import VaultService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    current_user: str = Depends(get_current_user),
    vault: VaultService = Depends(get_vault),
) -> DashboardResponse:
    """Aggregate next calendar event, open todos, and last note for the dashboard."""
    return await fetch_dashboard_data(current_user, vault)
