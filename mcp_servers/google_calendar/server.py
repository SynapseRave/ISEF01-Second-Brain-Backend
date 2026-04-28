"""Google Calendar MCP server.

Reads per-request credentials from the X-Service-Credentials header and
exposes Google Calendar operations as MCP tools.

Expected credentials JSON:
    {"access_token": "...", "refresh_token": "...", "expires_at": "..."}
"""

import json
import os
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

_credentials_var: ContextVar[dict] = ContextVar("credentials", default={})

server = Server("google-calendar-mcp")
sse = SseServerTransport("/messages/")

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_DEFAULT_TIMEZONE = ZoneInfo("Europe/Berlin")


def _get_service():
    creds_dict = _credentials_var.get()
    expiry = None
    expires_at = creds_dict.get("expires_at")
    if isinstance(expires_at, str) and expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            # google-auth compares against naive UTC datetimes internally
            expiry = expiry.astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            expiry = None
    creds = Credentials(
        token=creds_dict.get("access_token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri=_TOKEN_URI,
        client_id=_GOOGLE_CLIENT_ID,
        client_secret=_GOOGLE_CLIENT_SECRET,
        expiry=expiry,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _event_start(event: dict) -> str:
    return event.get("start", {}).get(
        "dateTime",
        event.get("start", {}).get("date", ""),
    )


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_DEFAULT_TIMEZONE)
    return parsed.astimezone(UTC)


def _default_search_window() -> tuple[str, str]:
    now = datetime.now(tz=UTC)
    start = now.replace(
        month=1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    end = now.replace(
        year=now.year + 1,
        month=12,
        day=31,
        hour=23,
        minute=59,
        second=59,
        microsecond=0,
    )
    return start.isoformat(), end.isoformat()


def _day_window_from_date(date_str: str) -> tuple[str, str]:
    parsed = datetime.fromisoformat(date_str)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    day_start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return day_start.isoformat(), day_end.isoformat()


def _find_matching_events(
    service,
    *,
    calendar_id: str,
    summary: str | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    list_kwargs = {
        "calendarId": calendar_id,
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": max_results,
    }
    if time_min:
        list_kwargs["timeMin"] = time_min
    if time_max:
        list_kwargs["timeMax"] = time_max
    if summary:
        list_kwargs["q"] = summary

    items = service.events().list(**list_kwargs).execute().get("items", [])
    if summary:
        summary_lower = summary.strip().lower()
        items = [
            ev
            for ev in items
            if ev.get("summary", "").strip().lower() == summary_lower
        ]
    return items


def _resolve_event(
    service,
    args: dict,
) -> tuple[dict | None, list[TextContent] | None]:
    calendar_id = args.get("calendar_id", "primary")
    event_id = args.get("event_id")
    if event_id:
        event = service.events().get(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()
        return event, None

    summary = (
        args.get("lookup_summary")
        or args.get("current_summary")
        or args.get("summary")
    )
    lookup_start = (
        args.get("lookup_start_datetime")
        or args.get("current_start_datetime")
    )
    time_min = args.get("time_min")
    time_max = args.get("time_max")
    date = args.get("date")
    if not summary:
        return (
            None,
            [
                TextContent(
                    type="text",
                    text=(
                        "Kein Termin gefunden. Bitte gib entweder event_id oder "
                        "summary plus geeignetes time_min/time_max an."
                    ),
                )
            ],
        )

    if date and not time_min and not time_max:
        time_min, time_max = _day_window_from_date(date)
    if not time_min and not time_max:
        time_min, time_max = _default_search_window()

    matches = _find_matching_events(
        service,
        calendar_id=calendar_id,
        summary=summary,
        time_min=time_min,
        time_max=time_max,
    )
    if lookup_start:
        requested_start = _parse_datetime(lookup_start)
        if requested_start is not None:
            matches = [
                ev
                for ev in matches
                if _parse_datetime(_event_start(ev)) == requested_start
            ]
    if not matches:
        return (
            None,
            [
                TextContent(
                    type="text",
                    text=(
                        f"Kein Termin mit dem Titel '{summary}' im angegebenen Zeitraum gefunden."
                    ),
                )
            ],
        )
    if len(matches) > 1:
        lines = [
            f"- [{ev.get('id','')}] {_event_start(ev)}: {ev.get('summary','(kein Titel)')}"
            for ev in matches
        ]
        return (
            None,
            [
                TextContent(
                    type="text",
                    text=(
                        "Mehrere passende Termine gefunden. Bitte verwende eine genauere Zeitspanne, "
                        "lookup_start_datetime oder die event_id:\n" + "\n".join(lines)
                    ),
                )
            ],
        )
    return matches[0], None


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
                    "time_max": {
                        "type": "string",
                        "description": "Spätestes Startdatum im ISO 8601 Format",
                    },
                    "date": {
                        "type": "string",
                        "description": "Optionales Datum im ISO-Format (YYYY-MM-DD), um Termine für genau diesen Tag zu listen",
                    },
                },
            },
        ),
        Tool(
            name="update_event",
            description="Aktualisiere einen bestehenden Termin im Google Kalender. Nutze bevorzugt event_id, alternativ kann der bestehende Termin über lookup_summary/current_summary und optional lookup_start_datetime gefunden werden.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "ID des zu aktualisierenden Termins",
                    },
                    "lookup_summary": {
                        "type": "string",
                        "description": "Aktueller/exakter Titel des bestehenden Termins, wenn per Titel gesucht werden soll",
                    },
                    "current_summary": {
                        "type": "string",
                        "description": "Alias für den aktuellen/exakten Titel des bestehenden Termins",
                    },
                    "lookup_start_datetime": {
                        "type": "string",
                        "description": "Aktuelle/exakte Startzeit des bestehenden Termins im ISO 8601 Format, um gleichnamige Termine eindeutig zu finden",
                    },
                    "current_start_datetime": {
                        "type": "string",
                        "description": "Alias für die aktuelle/exakte Startzeit des bestehenden Termins",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Neuer Titel des Termins",
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "Neue Startzeit im ISO 8601 Format",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "Neue Endzeit im ISO 8601 Format",
                    },
                    "description": {
                        "type": "string",
                        "description": "Neue Beschreibung des Termins",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Kalender-ID (Standard: 'primary')",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "Frühestes Startdatum im ISO 8601 Format, falls der Termin per Titel gesucht werden soll",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "Spätestes Startdatum im ISO 8601 Format, falls der Termin per Titel gesucht werden soll",
                    },
                    "date": {
                        "type": "string",
                        "description": "Optionales Datum im ISO-Format (YYYY-MM-DD), um den Suchzeitraum auf diesen Tag zu setzen",
                    },
                },
            },
        ),
        Tool(
            name="delete_event",
            description="Lösche einen bestehenden Termin im Google Kalender. Nutze bevorzugt event_id, alternativ kann der bestehende Termin über lookup_summary/current_summary und optional lookup_start_datetime gefunden werden.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "ID des zu löschenden Termins",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Kalender-ID (Standard: 'primary')",
                    },
                    "lookup_summary": {
                        "type": "string",
                        "description": "Aktueller/exakter Titel des bestehenden Termins, wenn per Titel gesucht werden soll",
                    },
                    "current_summary": {
                        "type": "string",
                        "description": "Alias für den aktuellen/exakten Titel des bestehenden Termins",
                    },
                    "lookup_start_datetime": {
                        "type": "string",
                        "description": "Aktuelle/exakte Startzeit des bestehenden Termins im ISO 8601 Format, um gleichnamige Termine eindeutig zu finden",
                    },
                    "current_start_datetime": {
                        "type": "string",
                        "description": "Alias für die aktuelle/exakte Startzeit des bestehenden Termins",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Titel des zu löschenden Termins",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "Frühestes Startdatum im ISO 8601 Format, falls der Termin per Titel gesucht werden soll",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "Spätestes Startdatum im ISO 8601 Format, falls der Termin per Titel gesucht werden soll",
                    },
                    "date": {
                        "type": "string",
                        "description": "Optionales Datum im ISO-Format (YYYY-MM-DD), um den Suchzeitraum auf diesen Tag zu setzen",
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
    if name == "update_event":
        return _update_event(arguments)
    if name == "delete_event":
        return _delete_event(arguments)
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
    event_id = event.get("id", "")
    return [
        TextContent(
            type="text",
            text=(
                f"Termin erstellt: {args['summary']}\n"
                f"Start: {args['start_datetime']}\n"
                f"event_id: {event_id}\n"
                f"deep_link: {event_link}"
            ),
        )
    ]


def _list_events(args: dict) -> list[TextContent]:
    service = _get_service()
    calendar_id = args.get("calendar_id", "primary")
    date = args.get("date")
    if date and not args.get("time_min") and not args.get("time_max"):
        time_min, time_max = _day_window_from_date(date)
    else:
        time_min = args.get(
            "time_min",
            datetime.now(tz=UTC).isoformat(),
        )
        time_max = args.get("time_max")
    max_results = args.get("max_results", 10)

    list_kwargs = {
        "calendarId": calendar_id,
        "timeMin": time_min,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if time_max:
        list_kwargs["timeMax"] = time_max

    events_result = service.events().list(**list_kwargs).execute()
    items = events_result.get("items", [])
    lines = []
    for ev in items:
        start = ev["start"].get("dateTime", ev["start"].get("date"))
        event_id = ev.get("id", "")
        summary = ev.get("summary", "(kein Titel)")
        lines.append(f"- [{event_id}] {start}: {summary}")
    return [
        TextContent(
            type="text",
            text="\n".join(lines) or "Keine Termine gefunden.",
        )
    ]


def _update_event(args: dict) -> list[TextContent]:
    service = _get_service()
    calendar_id = args.get("calendar_id", "primary")
    event, resolution_error = _resolve_event(service, args)
    if resolution_error is not None:
        return resolution_error
    assert event is not None
    event_id = event["id"]

    if "summary" in args and args["summary"]:
        event["summary"] = args["summary"]
    if "description" in args:
        event["description"] = args["description"]
    if "start_datetime" in args:
        event["start"] = {
            "dateTime": args["start_datetime"],
            "timeZone": "Europe/Berlin",
        }
    if "end_datetime" in args:
        event["end"] = {
            "dateTime": args["end_datetime"],
            "timeZone": "Europe/Berlin",
        }

    updated = (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=event)
        .execute()
    )
    summary = updated.get("summary", "(kein Titel)")
    start = updated.get("start", {}).get(
        "dateTime",
        updated.get("start", {}).get("date"),
    )
    event_link = updated.get("htmlLink", "")
    return [
        TextContent(
            type="text",
            text=(
                f"Termin aktualisiert: {summary}\n"
                f"Start: {start}\n"
                f"event_id: {event_id}\n"
                f"deep_link: {event_link}"
            ),
        )
    ]


def _delete_event(args: dict) -> list[TextContent]:
    service = _get_service()
    calendar_id = args.get("calendar_id", "primary")
    event, resolution_error = _resolve_event(service, args)
    if resolution_error is not None:
        return resolution_error
    assert event is not None
    event_id = event["id"]
    summary = event.get("summary", "(kein Titel)")
    start = _event_start(event)

    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    return [
        TextContent(
            type="text",
            text=(
                f"Termin gelöscht: {summary}\n"
                f"Start: {start}\n"
                f"event_id: {event_id}"
            ),
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
