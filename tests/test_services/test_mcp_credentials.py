import json
from unittest.mock import AsyncMock

import pytest

from app.schemas.credential import ApplicationService
from app.services.mcp.credentials import get_user_credentials_for_services


@pytest.mark.asyncio
async def test_returns_credentials_for_configured_services() -> None:
    creds_payload = {"api_token": "tok-123"}
    vault = AsyncMock()
    vault.retrieve = AsyncMock(return_value=json.dumps(creds_payload))

    result = await get_user_credentials_for_services(
        "user-1", [ApplicationService.notion], vault
    )

    assert ApplicationService.notion in result
    assert result[ApplicationService.notion] == creds_payload


@pytest.mark.asyncio
async def test_silently_skips_missing_services() -> None:
    vault = AsyncMock()
    vault.retrieve = AsyncMock(side_effect=KeyError("not found"))

    result = await get_user_credentials_for_services(
        "user-1", [ApplicationService.notion, ApplicationService.todoist], vault
    )

    assert result == {}


@pytest.mark.asyncio
async def test_partial_services_configured() -> None:
    notion_creds = {"api_token": "notion-tok"}

    async def _retrieve(path: str) -> str:
        if "notion" in path:
            return json.dumps(notion_creds)
        raise KeyError(path)

    vault = AsyncMock()
    vault.retrieve = AsyncMock(side_effect=_retrieve)

    result = await get_user_credentials_for_services(
        "user-1",
        [ApplicationService.notion, ApplicationService.todoist],
        vault,
    )

    assert list(result.keys()) == [ApplicationService.notion]
    assert result[ApplicationService.notion] == notion_creds


@pytest.mark.asyncio
async def test_empty_services_list_returns_empty_dict() -> None:
    vault = AsyncMock()
    result = await get_user_credentials_for_services("user-1", [], vault)
    assert result == {}
    vault.retrieve.assert_not_called()
