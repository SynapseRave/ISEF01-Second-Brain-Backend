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
from starlette.responses import JSONResponse, Response
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
        Tool(
            name="search_pages",
            description="Suche nach Seiten und Notizen in Notion anhand eines Stichworts",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Suchbegriff (Titel oder Inhalt)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="read_page",
            description="Lese den vollständigen Textinhalt einer Notion-Seite",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "ID der Notion-Seite",
                    },
                },
                "required": ["page_id"],
            },
        ),
        Tool(
            name="get_recent_page",
            description="Gibt die zuletzt bearbeitete Seite/Notiz aus Notion als JSON zurück",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = _get_client()
    try:
        if name == "create_page":
            return await _create_page(client, arguments)
        if name == "append_block":
            return await _append_block(client, arguments)
        if name == "query_database":
            return await _query_database(client, arguments)
        if name == "search_pages":
            return await _search_pages(client, arguments)
        if name == "read_page":
            return await _read_page(client, arguments)
        if name == "get_recent_page":
            return await _get_recent_page(client)
        return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Notion-Fehler: {exc}")]


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


async def _search_pages(
    client: AsyncClient, args: dict
) -> list[TextContent]:
    response = await client.search(
        query=args["query"],
        filter={"value": "page", "property": "object"},
    )
    results = response.get("results", [])
    lines = []
    for page in results[:10]:
        title_parts = (
            page.get("properties", {})
            .get("title", {})
            .get("title", [])
        )
        title = "".join(p.get("plain_text", "") for p in title_parts) or "(kein Titel)"
        page_id = page["id"]
        url = page.get("url", "")
        lines.append(f"- {title} | ID: {page_id} | {url}")
    return [
        TextContent(
            type="text",
            text="\n".join(lines) if lines else "Keine Seiten gefunden.",
        )
    ]


def _extract_text_from_blocks(blocks: list[dict]) -> str:
    lines = []
    for block in blocks:
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})
        rich_text = block_data.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text)
        if text:
            lines.append(text)
    return "\n".join(lines)


async def _read_page(
    client: AsyncClient, args: dict
) -> list[TextContent]:
    page_id = args["page_id"]
    page = await client.pages.retrieve(page_id=page_id)
    title_parts = (
        page.get("properties", {})
        .get("title", {})
        .get("title", [])
    )
    title = "".join(p.get("plain_text", "") for p in title_parts) or "(kein Titel)"

    all_blocks: list[dict] = []
    cursor = None
    while True:
        kwargs: dict = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = await client.blocks.children.list(**kwargs)
        all_blocks.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    content = _extract_text_from_blocks(all_blocks)
    return [
        TextContent(
            type="text",
            text=f"# {title}\n\n{content}" if content else f"# {title}\n\n(Seite hat keinen Textinhalt)",
        )
    ]


async def _get_recent_page(client: AsyncClient) -> list[TextContent]:
    response = await client.search(
        query="",
        filter={"value": "page", "property": "object"},
        sort={"direction": "descending", "timestamp": "last_edited_time"},
    )
    results = response.get("results", [])
    if not results:
        return [TextContent(type="text", text="{}")]
    page = results[0]
    title_parts = (
        page.get("properties", {}).get("title", {}).get("title", [])
    )
    title = "".join(p.get("plain_text", "") for p in title_parts) or "(kein Titel)"
    return [
        TextContent(
            type="text",
            text=json.dumps({
                "id": page["id"],
                "title": title,
                "url": page.get("url", ""),
                "last_edited": page.get("last_edited_time", ""),
            }, ensure_ascii=False),
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
