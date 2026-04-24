"""Notion MCP server.

Reads per-request credentials from the X-Service-Credentials header and
exposes Notion operations as MCP tools.

Expected credentials JSON:
    {"api_token": "<integration_token>"}
"""

import json
from contextvars import ContextVar

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from notion_client import AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

_credentials_var: ContextVar[dict] = ContextVar("credentials", default={})

server = Server("notion-mcp")
sse = SseServerTransport("/messages/")


def _get_client() -> AsyncClient:
    creds = _credentials_var.get()
    token = creds.get("api_token", "")
    return AsyncClient(auth=token)


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_page",
            description="Erstelle eine neue Seite in Notion",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Titel der Seite"},
                    "content": {
                        "type": "string",
                        "description": "Textinhalt der Seite (Markdown)",
                    },
                    "parent_page_id": {
                        "type": "string",
                        "description": "ID der übergeordneten Seite oder Datenbank",
                    },
                },
                "required": ["title", "content", "parent_page_id"],
            },
        ),
        Tool(
            name="append_block",
            description="Hänge Text-Inhalt an eine bestehende Notion-Seite an",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "ID der Notion-Seite"},
                    "content": {"type": "string", "description": "Anzuhängender Text"},
                },
                "required": ["page_id", "content"],
            },
        ),
        Tool(
            name="query_database",
            description="Frage eine Notion-Datenbank ab",
            inputSchema={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "ID der Notion-Datenbank",
                    },
                    "filter_property": {
                        "type": "string",
                        "description": "Optionaler Filterausdruck",
                    },
                },
                "required": ["database_id"],
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = _get_client()
    if name == "create_page":
        return await _create_page(client, arguments)
    if name == "append_block":
        return await _append_block(client, arguments)
    if name == "query_database":
        return await _query_database(client, arguments)
    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def _create_page(
    client: AsyncClient, args: dict
) -> list[TextContent]:
    response = await client.pages.create(
        parent={"page_id": args["parent_page_id"]},
        properties={"title": [{"text": {"content": args["title"]}}]},
        children=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": args["content"]}}]
                },
            }
        ],
    )
    page_id = response["id"]
    page_url = response.get("url", "")
    return [
        TextContent(
            type="text",
            text=f"Seite erstellt: {args['title']}\ndeep_link: {page_url}\nID: {page_id}",
        )
    ]


async def _append_block(
    client: AsyncClient, args: dict
) -> list[TextContent]:
    await client.blocks.children.append(
        block_id=args["page_id"],
        children=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": args["content"]}}
                    ]
                },
            }
        ],
    )
    return [TextContent(type="text", text="Inhalt erfolgreich angehängt.")]


async def _query_database(
    client: AsyncClient, args: dict
) -> list[TextContent]:
    response = await client.databases.query(database_id=args["database_id"])
    results = response.get("results", [])
    summary = json.dumps(results[:10], ensure_ascii=False)
    return [TextContent(type="text", text=summary)]


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
