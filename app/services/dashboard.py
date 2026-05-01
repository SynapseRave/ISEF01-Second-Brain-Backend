import json
import logging
import re
from datetime import UTC, datetime

from app.schemas.credential import ApplicationService
from app.schemas.dashboard import (
    CalendarEventSchema,
    DashboardResponse,
    NoteSchema,
    TodoSchema,
)
from app.services.mcp import get_mcp_client
from app.services.mcp.credentials import get_user_credentials_for_services
from app.services.vault.base import VaultService

logger = logging.getLogger(__name__)

_CALENDAR_LINE = re.compile(r"^\-\s+\[([^\]]+)\]\s+([^:]+):\s+(.+)$")
_TODO_LINE = re.compile(r"^\-\s+\[([^\]]+)\]\s+(.+)$")


async def fetch_dashboard_data(user_id: str, vault: VaultService) -> DashboardResponse:
    """Fetch next event, open todos, and last note from connected MCP services.

    Args:
        user_id: Keycloak subject ID of the requesting user.
        vault: Decryption backend for service credentials.

    Returns:
        Aggregated dashboard data; missing services are silently skipped.
    """
    mcp = get_mcp_client()
    creds = await get_user_credentials_for_services(
        user_id,
        list(ApplicationService),
        vault,
    )

    next_event = await _fetch_next_event(mcp, creds)
    todos = await _fetch_todos(mcp, creds)
    last_note = await _fetch_last_note(mcp, creds)

    return DashboardResponse(next_event=next_event, todos=todos, last_note=last_note)


async def _fetch_next_event(mcp, creds: dict) -> CalendarEventSchema | None:
    cal = ApplicationService("google_calendar")
    if cal not in creds:
        return None
    try:
        now = datetime.now(tz=UTC).isoformat()
        result = await mcp.call_tool(
            cal,
            "list_events",
            {"time_min": now, "max_results": 1},
            creds[cal],
        )
        text = _first_text(result)
        if not text or text.startswith("Keine"):
            return None
        for line in text.splitlines():
            m = _CALENDAR_LINE.match(line.strip())
            if m:
                event_id, start_raw, title = m.group(1), m.group(2), m.group(3)
                try:
                    start_time = datetime.fromisoformat(start_raw.strip())
                except ValueError:
                    return None
                return CalendarEventSchema(
                    id=event_id, title=title.strip(), start_time=start_time
                )
    except Exception:
        logger.exception("Dashboard: Google Calendar fetch failed")
    return None


async def _fetch_todos(mcp, creds: dict) -> list[TodoSchema]:
    todoist = ApplicationService("todoist")
    if todoist not in creds:
        return []
    try:
        result = await mcp.call_tool(todoist, "list_tasks", {}, creds[todoist])
        text = _first_text(result)
        if not text or text.startswith("Keine"):
            return []
        items: list[TodoSchema] = []
        for line in text.splitlines():
            m = _TODO_LINE.match(line.strip())
            if m and len(items) < 5:
                items.append(TodoSchema(id=m.group(1), title=m.group(2).strip()))
        return items
    except Exception:
        logger.exception("Dashboard: Todoist fetch failed")
    return []


async def _fetch_last_note(mcp, creds: dict) -> NoteSchema | None:
    notion = ApplicationService("notion")
    if notion not in creds:
        return None
    try:
        result = await mcp.call_tool(notion, "get_recent_page", {}, creds[notion])
        text = _first_text(result)
        if not text:
            return None
        data = json.loads(text)
        if not data.get("id"):
            return None
        return NoteSchema(
            id=data["id"],
            title=data.get("title", "(kein Titel)"),
            url=data.get("url", ""),
        )
    except Exception:
        logger.exception("Dashboard: Notion fetch failed")
    return None


def _first_text(result) -> str:
    for block in result.content:
        text = getattr(block, "text", None) or block.get("text", "")
        if text:
            return text
    return ""
