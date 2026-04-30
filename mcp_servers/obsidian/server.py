"""Obsidian MCP server.

Communicates with the Obsidian Local REST API plugin
(https://github.com/coddingtonbear/obsidian-local-rest-api).

Reads per-request credentials from the X-Service-Credentials header.

Expected credentials JSON:
    {"api_key": "<obsidian_rest_api_key>", "base_url": "http://host:27123"}
"""

import json
from contextvars import ContextVar

import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

_credentials_var: ContextVar[dict] = ContextVar("credentials", default={})

server = Server("obsidian-mcp")
sse = SseServerTransport("/messages/")


def _get_http_client() -> tuple[httpx.AsyncClient, str]:
    creds = _credentials_var.get()
    base_url = creds.get("base_url", "http://localhost:27123")
    api_key = creds.get("api_key", "")
    client = httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        verify=False,  # Obsidian REST API uses self-signed cert by default
        timeout=10,
    )
    return client, base_url


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_note",
            description="Erstelle eine neue Notiz in Obsidian",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Pfad der Notiz inkl. .md Endung (z.B. 'Notizen/Meeting.md')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Inhalt der Notiz (Markdown)",
                    },
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="append_to_note",
            description="Hänge Text an eine bestehende Obsidian-Notiz an",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Pfad der bestehenden Notiz",
                    },
                    "content": {"type": "string", "description": "Anzuhängender Text"},
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="search",
            description="Suche in Obsidian-Notizen nach einem Begriff",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Suchbegriff"},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    client, base_url = _get_http_client()
    async with client:
        if name == "create_note":
            return await _create_note(client, base_url, arguments)
        if name == "append_to_note":
            return await _append_to_note(client, base_url, arguments)
        if name == "search":
            return await _search(client, arguments)
    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def _create_note(
    client: httpx.AsyncClient, base_url: str, args: dict
) -> list[TextContent]:
    path = args["path"]
    resp = await client.put(
        f"/vault/{path}",
        content=args["content"].encode(),
        headers={"Content-Type": "text/markdown"},
    )
    resp.raise_for_status()
    note_url = f"{base_url}/vault/{path}"
    return [
        TextContent(
            type="text",
            text=f"Notiz erstellt: {path}\ndeep_link: obsidian://open?path={path}",
        )
    ]


async def _append_to_note(
    client: httpx.AsyncClient, base_url: str, args: dict
) -> list[TextContent]:
    path = args["path"]
    resp = await client.post(
        f"/vault/{path}",
        content=f"\n{args['content']}".encode(),
        headers={"Content-Type": "text/markdown"},
    )
    resp.raise_for_status()
    return [TextContent(type="text", text=f"Inhalt an {path} angehängt.")]


async def _search(client: httpx.AsyncClient, args: dict) -> list[TextContent]:
    resp = await client.post(
        "/search/simple/",
        params={"query": args["query"], "contextLength": 100},
    )
    resp.raise_for_status()
    results = resp.json()
    lines = [r.get("filename", "") for r in results[:10]]
    return [
        TextContent(
            type="text",
            text="\n".join(lines) or "Keine Ergebnisse gefunden.",
        )
    ]


async def _handle_sse(request: Request):
    raw = request.headers.get("X-Service-Credentials", "{}")
    token = _credentials_var.set(json.loads(raw))
    try:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )
    finally:
        _credentials_var.reset(token)
    return Response()


async def _health(_: Request):
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/sse", endpoint=_handle_sse),
        Route("/health", endpoint=_health),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)
