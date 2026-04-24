from app.services.mcp.client import MCPClient

_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """Return the shared MCPClient instance (lazy singleton).

    MCPClient is stateless — safe to share across requests. Credentials are
    passed per call, not stored in the client.
    """
    global _client
    if _client is None:
        _client = MCPClient()
    return _client
