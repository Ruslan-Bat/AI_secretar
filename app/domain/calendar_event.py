"""Модель события календаря, не зависящая от БД и внешнего API."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_id: str
    title: str
    start: datetime | date
    end: datetime | date
    html_link: str | None = None
