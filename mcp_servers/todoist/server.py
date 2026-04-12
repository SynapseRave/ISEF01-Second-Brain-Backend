"""Todoist MCP server.

Reads per-request credentials from the X-Service-Credentials header and
exposes Todoist task operations as MCP tools.

Expected credentials JSON:
    {"api_token": "<todoist_api_token>"}
"""

import json
from contextvars import ContextVar

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from todoist_api_python.api_async import TodoistAPIAsync

_credentials_var: ContextVar[dict] = ContextVar("credentials", default={})

server = Server("todoist-mcp")
sse = SseServerTransport("/messages/")


def _get_client() -> TodoistAPIAsync:
    creds = _credentials_var.get()
    return TodoistAPIAsync(creds.get("api_token", ""))


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_task",
            description="Erstelle eine neue Aufgabe in Todoist",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Aufgabentitel / Beschreibung",
                    },
                    "due_string": {
                        "type": "string",
                        "description": "Fälligkeitsdatum in natürlicher Sprache (z.B. 'morgen', 'nächsten Montag')",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priorität 1 (normal) bis 4 (sehr hoch)",
                        "minimum": 1,
                        "maximum": 4,
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Optionale Projekt-ID",
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="list_tasks",
            description="Liste offene Aufgaben in Todoist auf",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Todoist-Filterausdruck (z.B. 'today', 'p1')",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Nur Aufgaben aus diesem Projekt anzeigen",
                    },
                },
            },
        ),
        Tool(
            name="complete_task",
            description="Markiere eine Aufgabe als erledigt",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID der Aufgabe"},
                },
                "required": ["task_id"],
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    client = _get_client()
    if name == "create_task":
        return await _create_task(client, arguments)
    if name == "list_tasks":
        return await _list_tasks(client, arguments)
    if name == "complete_task":
        return await _complete_task(client, arguments)
    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def _create_task(client: TodoistAPIAsync, args: dict) -> list[TextContent]:
    kwargs = {"content": args["content"]}
    if "due_string" in args:
        kwargs["due_string"] = args["due_string"]
    if "priority" in args:
        kwargs["priority"] = args["priority"]
    if "project_id" in args:
        kwargs["project_id"] = args["project_id"]

    task = await client.add_task(**kwargs)
    return [
        TextContent(
            type="text",
            text=(
                f"Aufgabe erstellt: {task.content}\n"
                f"ID: {task.id}\n"
                f"deep_link: https://todoist.com/app/task/{task.id}"
            ),
        )
    ]


async def _list_tasks(client: TodoistAPIAsync, args: dict) -> list[TextContent]:
    kwargs = {}
    if "filter" in args:
        kwargs["filter"] = args["filter"]
    if "project_id" in args:
        kwargs["project_id"] = args["project_id"]

    tasks = await client.get_tasks(**kwargs)
    lines = [f"- [{t.id}] {t.content}" for t in tasks[:20]]
    return [TextContent(type="text", text="\n".join(lines) or "Keine Aufgaben gefunden.")]


async def _complete_task(client: TodoistAPIAsync, args: dict) -> list[TextContent]:
    await client.close_task(task_id=args["task_id"])
    return [TextContent(type="text", text=f"Aufgabe {args['task_id']} erledigt.")]


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
