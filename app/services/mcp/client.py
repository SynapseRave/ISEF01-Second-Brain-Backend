import json
from dataclasses import dataclass, field

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool

from app.core.config import settings
from app.core.exceptions import SecondBrainException
from app.schemas.credential import ApplicationService


@dataclass
class ToolCallResult:
    """Result of a single MCP tool call."""

    tool_name: str
    service: ApplicationService
    content: list[dict] = field(default_factory=list)
    is_error: bool = False
    deep_link: str | None = None


class MCPClient:
    """HTTP/SSE client for communicating with MCP server containers.

    Opens a fresh SSE connection per call — connections are not persistent.
    User credentials are injected as an HTTP header on each request so the
    shared containers remain stateless across multiple users.
    """

    def __init__(self, timeout: int | None = None) -> None:
        self._timeout = timeout or settings.mcp_timeout_seconds

    def _get_server_url(self, service: ApplicationService) -> str:
        url = settings.mcp_server_urls.get(service.value)
        if not url:
            raise SecondBrainException(
                f"Kein MCP-Server konfiguriert für: {service.value}",
                status_code=503,
            )
        return url

    def _credential_headers(self, credentials: dict) -> dict[str, str]:
        return {"X-Service-Credentials": json.dumps(credentials)}

    async def list_tools(
        self, service: ApplicationService, credentials: dict
    ) -> list[Tool]:
        """Connect to the MCP server and return its tool definitions.

        Args:
            service: Which MCP server to query.
            credentials: Decrypted credential dict for this user + service.

        Returns:
            List of MCP Tool objects.

        Raises:
            SecondBrainException: On connection error or timeout.
        """
        server_url = self._get_server_url(service)
        headers = self._credential_headers(credentials)
        try:
            async with sse_client(
                url=f"{server_url}/sse",
                headers=headers,
                timeout=self._timeout,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return result.tools
        except SecondBrainException:
            raise
        except Exception as exc:
            raise SecondBrainException(
                f"MCP-Verbindungsfehler ({service.value}): {exc}",
                status_code=503,
            ) from exc

    async def call_tool(
        self,
        service: ApplicationService,
        tool_name: str,
        args: dict,
        credentials: dict,
    ) -> ToolCallResult:
        """Execute a tool on the target MCP server.

        Args:
            service: Which MCP server to use.
            tool_name: The MCP tool identifier (e.g. "create_page").
            args: Tool arguments as decided by the LLM.
            credentials: Decrypted user credentials for this service.

        Returns:
            ToolCallResult with content and optional deep_link.

        Raises:
            SecondBrainException: On connection or execution error.
        """
        server_url = self._get_server_url(service)
        headers = self._credential_headers(credentials)
        try:
            async with sse_client(
                url=f"{server_url}/sse",
                headers=headers,
                timeout=self._timeout,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, args)
                    content = [c.model_dump() for c in result.content]
                    deep_link = _extract_deep_link(result.content)
                    return ToolCallResult(
                        tool_name=tool_name,
                        service=service,
                        content=content,
                        is_error=result.isError or False,
                        deep_link=deep_link,
                    )
        except SecondBrainException:
            raise
        except Exception as exc:
            raise SecondBrainException(
                f"MCP-Werkzeugfehler ({service.value}/{tool_name}): {exc}",
                status_code=502,
            ) from exc

    async def health_check(self, service: ApplicationService) -> bool:
        """Ping the MCP server's health endpoint without credentials.

        Args:
            service: Which MCP server to ping.

        Returns:
            True if the server responds with HTTP 200.
        """
        server_url = self._get_server_url(service)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{server_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


def _extract_deep_link(content: list) -> str | None:
    """Extract a deep link URL from MCP content blocks.

    Convention: MCP servers may include a line ``deep_link: <url>`` anywhere
    in a text content block. The first occurrence wins.
    """
    for block in content:
        text = getattr(block, "text", None)
        if not text:
            continue
        for line in text.splitlines():
            if line.startswith("deep_link:"):
                return line.split(":", 1)[1].strip()
    return None
