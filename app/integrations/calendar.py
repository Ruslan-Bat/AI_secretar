"""Интерфейс календаря, используемый сервисами приложения."""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.calendar_event import CalendarEvent


@runtime_checkable
class CalendarGateway(Protocol):
    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
        user_credentials: Any | None = None,
    ) -> list[CalendarEvent]:
        """Возвращает ближайшие события, отсортированные по времени начала."""
        ...

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        user_credentials: Any | None = None,
    ) -> CalendarEvent:
        """Создаёт и возвращает событие с заданным временем."""
        ...
        
    async def delete_event(self, event_id: str, user_credentials: Any | None = None) -> None:
        """Удаляет событие по идентификатору Google Calendar."""

    async def get_primary_calendar_timezone(self, user_credentials: Any | None = None) -> str:
        """Возвращает IANA-имя часового пояса основного календаря пользователя."""
        ...

    async def update_event(
        self,
        event_id: str,
        *,
        start: datetime,
        end: datetime,
        user_credentials: Any | None = None,
    ) -> CalendarEvent:
        """Частично обновляет событие, сохраняя незатронутые поля."""
        ...