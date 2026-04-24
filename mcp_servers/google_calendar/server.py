"""Google Calendar MCP server.

Reads per-request credentials from the X-Service-Credentials header and
exposes Google Calendar operations as MCP tools.

Expected credentials JSON:
    {"access_token": "...", "refresh_token": "...", "expires_at": "..."}
"""

import json
from contextvars import ContextVar
from datetime import UTC, datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

_credentials_var: ContextVar[dict] = ContextVar("credentials", default={})

server = Server("google-calendar-mcp")
sse = SseServerTransport("/messages/")

_GOOGLE_CLIENT_ID = ""
_GOOGLE_CLIENT_SECRET = ""
_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _get_service():
    creds_dict = _credentials_var.get()
    creds = Credentials(
        token=creds_dict.get("access_token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=_TOKEN_URI,
        client_id=_GOOGLE_CLIENT_ID,
        client_secret=_GOOGLE_CLIENT_SECRET,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_event",
            description="Erstelle einen neuen Termin im Google Kalender",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Titel des Termins",
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "Startzeit im ISO 8601 Format (z.B. 2025-04-15T10:00:00)",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "Endzeit im ISO 8601 Format",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optionale Beschreibung",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Kalender-ID (Standard: 'primary')",
                    },
                },
                "required": ["summary", "start_datetime", "end_datetime"],
            },
        ),
        Tool(
            name="list_events",
            description="Liste bevorstehende Termine im Google Kalender auf",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Maximale Anzahl zurückgegebener Termine",
                        "default": 10,
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Kalender-ID (Standard: 'primary')",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "Frühestes Startdatum im ISO 8601 Format",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "create_event":
        return _create_event(arguments)
    if name == "list_events":
        return _list_events(arguments)
    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


def _create_event(args: dict) -> list[TextContent]:
    service = _get_service()
    calendar_id = args.get("calendar_id", "primary")
    event_body = {
        "summary": args["summary"],
        "start": {"dateTime": args["start_datetime"], "timeZone": "Europe/Berlin"},
        "end": {"dateTime": args["end_datetime"], "timeZone": "Europe/Berlin"},
    }
    if "description" in args:
        event_body["description"] = args["description"]

    event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    event_link = event.get("htmlLink", "")
    return [
        TextContent(
            type="text",
            text=(
                f"Termin erstellt: {args['summary']}\n"
                f"Start: {args['start_datetime']}\n"
                f"deep_link: {event_link}"
            ),
        )
    ]


def _list_events(args: dict) -> list[TextContent]:
    service = _get_service()
    calendar_id = args.get("calendar_id", "primary")
    time_min = args.get(
        "time_min",
        datetime.now(tz=UTC).isoformat(),
    )
    max_results = args.get("max_results", 10)

    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = events_result.get("items", [])
    lines = []
    for ev in items:
        start = ev["start"].get("dateTime", ev["start"].get("date"))
        lines.append(f"- {start}: {ev.get('summary', '(kein Titel)')}")
    return [
        TextContent(
            type="text",
            text="\n".join(lines) or "Keine Termine gefunden.",
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
