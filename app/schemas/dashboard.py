from datetime import datetime

from pydantic import BaseModel


class CalendarEventSchema(BaseModel):
    id: str
    title: str
    start_time: datetime
    source_service: str = "google_calendar"


class TodoSchema(BaseModel):
    id: str
    title: str
    source_service: str = "todoist"


class NoteSchema(BaseModel):
    id: str
    title: str
    url: str
    source_service: str = "notion"


class DashboardResponse(BaseModel):
    next_event: CalendarEventSchema | None = None
    todos: list[TodoSchema] = []
    last_note: NoteSchema | None = None
