"""OneNote MCP server.

Communicates with the Microsoft Graph API to manage OneNote notebooks.

Reads per-request credentials from the X-Service-Credentials header.

Expected credentials JSON:
    {"access_token": "...", "refresh_token": "..."}
"""

import json
from contextvars import ContextVar

import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

_credentials_var: ContextVar[dict] = ContextVar("credentials", default={})

server = Server("onenote-mcp")
sse = SseServerTransport("/messages/")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_http_client() -> httpx.AsyncClient:
    creds = _credentials_var.get()
    access_token = creds.get("access_token", "")
    return httpx.AsyncClient(
        base_url=_GRAPH_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_page",
            description="Erstelle eine neue Seite in OneNote",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Seitentitel"},
                    "content": {
                        "type": "string",
                        "description": "HTML-Inhalt der Seite",
                    },
                    "section_id": {
                        "type": "string",
                        "description": "ID des Abschnitts, in dem die Seite erstellt werden soll",
                    },
                },
                "required": ["title", "content", "section_id"],
            },
        ),
        Tool(
            name="list_notebooks",
            description="Liste verfügbare OneNote-Notizbücher auf",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_sections",
            description="Liste Abschnitte in einem OneNote-Notizbuch auf",
            inputSchema={
                "type": "object",
                "properties": {
                    "notebook_id": {
                        "type": "string",
                        "description": "ID des Notizbuchs",
                    },
                },
                "required": ["notebook_id"],
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with _get_http_client() as client:
        if name == "create_page":
            return await _create_page(client, arguments)
        if name == "list_notebooks":
            return await _list_notebooks(client)
        if name == "list_sections":
            return await _list_sections(client, arguments)
    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def _create_page(
    client: httpx.AsyncClient, args: dict
) -> list[TextContent]:
    section_id = args["section_id"]
    html_content = (
        f"<!DOCTYPE html><html><head><title>{args['title']}</title></head>"
        f"<body>{args['content']}</body></html>"
    )
    resp = await client.post(
        f"/me/onenote/sections/{section_id}/pages",
        content=html_content.encode("utf-8"),
        headers={"Content-Type": "application/xhtml+xml"},
    )
    resp.raise_for_status()
    data = resp.json()
    page_url = data.get("links", {}).get("oneNoteWebUrl", {}).get("href", "")
    return [
        TextContent(
            type="text",
            text=(
                f"OneNote-Seite erstellt: {args['title']}\n"
                f"deep_link: {page_url}"
            ),
        )
    ]


async def _list_notebooks(client: httpx.AsyncClient) -> list[TextContent]:
    resp = await client.get("/me/onenote/notebooks")
    resp.raise_for_status()
    notebooks = resp.json().get("value", [])
    lines = [f"- [{nb['id']}] {nb['displayName']}" for nb in notebooks]
    return [
        TextContent(
            type="text",
            text="\n".join(lines) or "Keine Notizbücher gefunden.",
        )
    ]


async def _list_sections(
    client: httpx.AsyncClient, args: dict
) -> list[TextContent]:
    notebook_id = args["notebook_id"]
    resp = await client.get(f"/me/onenote/notebooks/{notebook_id}/sections")
    resp.raise_for_status()
    sections = resp.json().get("value", [])
    lines = [f"- [{s['id']}] {s['displayName']}" for s in sections]
    return [
        TextContent(
            type="text",
            text="\n".join(lines) or "Keine Abschnitte gefunden.",
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


async def _health(_: Request):
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/sse", endpoint=_handle_sse),
        Route("/health", endpoint=_health),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)
