import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import SecondBrainException
from app.schemas.credential import ApplicationService
from app.services.mcp.client import MCPClient, ToolCallResult, _extract_deep_link


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    return block


# ---------------------------------------------------------------------------
# _extract_deep_link
# ---------------------------------------------------------------------------


def test_extract_deep_link_finds_link() -> None:
    block = _make_text_block("Seite erstellt\ndeep_link: https://notion.so/abc")
    assert _extract_deep_link([block]) == "https://notion.so/abc"


def test_extract_deep_link_returns_none_when_absent() -> None:
    block = _make_text_block("Kein Link hier")
    assert _extract_deep_link([block]) is None


def test_extract_deep_link_returns_none_for_empty_content() -> None:
    assert _extract_deep_link([]) is None


def test_extract_deep_link_returns_first_match() -> None:
    b1 = _make_text_block("deep_link: https://first.example")
    b2 = _make_text_block("deep_link: https://second.example")
    assert _extract_deep_link([b1, b2]) == "https://first.example"


# ---------------------------------------------------------------------------
# MCPClient._get_server_url
# ---------------------------------------------------------------------------


def test_get_server_url_raises_for_unconfigured_service() -> None:
    client = MCPClient()
    with patch("app.services.mcp.client.settings") as mock_cfg:
        mock_cfg.mcp_server_urls = {}
        mock_cfg.mcp_timeout_seconds = 30
        with pytest.raises(SecondBrainException) as exc_info:
            client._get_server_url(ApplicationService.notion)
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# MCPClient.list_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_tools() -> None:
    fake_tool = MagicMock()
    fake_tool.name = "create_page"

    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.initialize = AsyncMock()
    fake_session.list_tools = AsyncMock(return_value=MagicMock(tools=[fake_tool]))

    fake_streams = AsyncMock()
    fake_streams.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    fake_streams.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.mcp.client.settings") as mock_cfg,
        patch("app.services.mcp.client.sse_client", return_value=fake_streams),
        patch("app.services.mcp.client.ClientSession", return_value=fake_session),
    ):
        mock_cfg.mcp_server_urls = {"notion": "http://localhost:3001"}
        mock_cfg.mcp_timeout_seconds = 5

        client = MCPClient()
        tools = await client.list_tools(ApplicationService.notion, {"api_token": "tok"})
        assert tools == [fake_tool]


@pytest.mark.asyncio
async def test_list_tools_wraps_connection_error() -> None:
    fake_streams = AsyncMock()
    fake_streams.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
    fake_streams.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.mcp.client.settings") as mock_cfg,
        patch("app.services.mcp.client.sse_client", return_value=fake_streams),
    ):
        mock_cfg.mcp_server_urls = {"notion": "http://localhost:3001"}
        mock_cfg.mcp_timeout_seconds = 5

        client = MCPClient()
        with pytest.raises(SecondBrainException) as exc_info:
            await client.list_tools(ApplicationService.notion, {})
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# MCPClient.call_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_tool_returns_result_with_deep_link() -> None:
    content_block = _make_text_block("Erstellt!\ndeep_link: https://notion.so/page1")
    content_block.model_dump = MagicMock(
        return_value={"type": "text", "text": content_block.text}
    )

    fake_result = MagicMock()
    fake_result.content = [content_block]
    fake_result.isError = False

    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.initialize = AsyncMock()
    fake_session.call_tool = AsyncMock(return_value=fake_result)

    fake_streams = AsyncMock()
    fake_streams.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    fake_streams.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.mcp.client.settings") as mock_cfg,
        patch("app.services.mcp.client.sse_client", return_value=fake_streams),
        patch("app.services.mcp.client.ClientSession", return_value=fake_session),
    ):
        mock_cfg.mcp_server_urls = {"notion": "http://localhost:3001"}
        mock_cfg.mcp_timeout_seconds = 5

        client = MCPClient()
        result = await client.call_tool(
            ApplicationService.notion, "create_page", {"title": "Test"}, {}
        )

    assert isinstance(result, ToolCallResult)
    assert result.tool_name == "create_page"
    assert result.deep_link == "https://notion.so/page1"
    assert result.is_error is False


@pytest.mark.asyncio
async def test_call_tool_wraps_execution_error() -> None:
    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.initialize = AsyncMock()
    fake_session.call_tool = AsyncMock(side_effect=RuntimeError("API error"))

    fake_streams = AsyncMock()
    fake_streams.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    fake_streams.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.mcp.client.settings") as mock_cfg,
        patch("app.services.mcp.client.sse_client", return_value=fake_streams),
        patch("app.services.mcp.client.ClientSession", return_value=fake_session),
    ):
        mock_cfg.mcp_server_urls = {"notion": "http://localhost:3001"}
        mock_cfg.mcp_timeout_seconds = 5

        client = MCPClient()
        with pytest.raises(SecondBrainException) as exc_info:
            await client.call_tool(ApplicationService.notion, "create_page", {}, {})
        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# MCPClient._credential_headers
# ---------------------------------------------------------------------------


def test_credential_headers_serialize_to_json() -> None:
    client = MCPClient()
    creds = {"api_token": "secret"}
    headers = client._credential_headers(creds)
    assert json.loads(headers["X-Service-Credentials"]) == creds
