"""Интерфейс календаря, используемый сервисами приложения."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.calendar_event import CalendarEvent


@runtime_checkable
class CalendarGateway(Protocol):
    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
    ) -> list[CalendarEvent]:
        """Возвращает ближайшие события, отсортированные по времени начала."""
        ...

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
    ) -> CalendarEvent:
        """Создаёт и возвращает событие с заданным временем."""
        ...
        
    async def delete_event(self, event_id: str) -> None:
        """Удаляет событие по идентификатору Google Calendar."""
