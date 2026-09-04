"""Слой исполнения инструментов AI-ассистента."""

from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable

from pydantic import ValidationError

from app.core.ai_exceptions import ToolArgumentError, UnknownToolError
from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
    CalendarIntegrationError,
    CalendarTokenRefreshError,
    EventNotFoundError,
)
from app.domain.ai import (
    CreateEventInput,
    GetEventsInput,
    GetFreeSlotsInput,
    MoveEventInput,
)
from app.domain.calendar_event import CalendarEvent
from app.services.calendar import CalendarService


class ToolExecutor:
    """Выполняет операции, вызываемые через tool calling.

    Контракт execute():
    - Успех (включая ожидаемые бизнес-ошибки вроде "нужна авторизация")
      -> возвращает str с текстом для модели.
    - Невалидные аргументы от модели -> бросает ToolArgumentError.
    - Неизвестное имя инструмента -> бросает UnknownToolError.
    Вызывающий код обязан ловить оба типа отдельно.
    """

    def __init__(self, calendar_service: CalendarService) -> None:
        self._calendar_service = calendar_service
        self._handlers: dict[str, Callable[[dict, int], Awaitable[str]]] = {
            "create_event": self._create_event,
            "get_events": self._get_events,
            "get_free_slots": self._get_free_slots,
            "move_event": self._move_event,
        }

    async def execute(self, tool_name: str, arguments: dict, user_id: int) -> str:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise UnknownToolError(tool_name)
        return await handler(arguments, user_id)

    # --- Инструменты -----------------------------------------------------

    async def _create_event(self, arguments: dict, user_id: int) -> str:
        payload = self._validate("create_event", CreateEventInput, arguments)

        command_args = (
            f"{payload.start_date.isoformat()} "
            f"{payload.start_time.strftime('%H:%M')} "
            f"{payload.duration_minutes} {payload.title}"
        )
        try:
            event = await self._calendar_service.create_from_text(command_args, user_id)
        except (
            CalendarInputError,
            CalendarAuthRequiredError,
            CalendarTokenRefreshError,
            CalendarIntegrationError,
            EventNotFoundError,
        ) as error:
            return self._describe_calendar_error(error)

        return (
            f"Событие создано на {payload.start_date.isoformat()} "
            f"в {payload.start_time.strftime('%H:%M')}. ID: {event.event_id}"
        )

    async def _get_events(self, arguments: dict, user_id: int) -> str:
        payload = self._validate("get_events", GetEventsInput, arguments)

        try:
            events = await self._calendar_service.get_events(
                start_day_offset=payload.start_day_offset,
                end_day_offset=payload.end_day_offset,
                telegram_id=user_id,
            )
        except (
            CalendarInputError,
            CalendarAuthRequiredError,
            CalendarTokenRefreshError,
            CalendarIntegrationError,
            EventNotFoundError,
        ) as error:
            return self._describe_calendar_error(error)

        if not events:
            return (
                "На указанный период событий нет — календарь свободен. "
                "Это нормальный результат, а не ошибка."
            )

        lines = [self._format_event(event) for event in events]
        return "Найденные события:\n" + "\n".join(lines)

    async def _get_free_slots(self, arguments: dict, user_id: int) -> str:
        payload = self._validate("get_free_slots", GetFreeSlotsInput, arguments)

        try:
            slots = await self._calendar_service.get_free_slots(
                start_day_offset=payload.start_day_offset,
                end_day_offset=payload.end_day_offset,
                telegram_id=user_id,
                min_duration_minutes=payload.min_duration_minutes,
            )
        except (
            CalendarInputError,
            CalendarAuthRequiredError,
            CalendarTokenRefreshError,
            CalendarIntegrationError,
            EventNotFoundError,
        ) as error:
            return self._describe_calendar_error(error)

        if not slots:
            return (
                f"Свободных окон длительностью от {payload.min_duration_minutes} мин "
                "в указанном периоде нет. Это нормальный результат, а не ошибка. "
                "Предложи пользователю другой период или меньшую длительность."
            )

        lines = [self._format_slot(start, end) for start, end in slots]
        return "Свободные окна:\n" + "\n".join(lines)

    async def _move_event(self, arguments: dict, user_id: int) -> str:
        payload = self._validate("move_event", MoveEventInput, arguments)

        try:
            event = await self._calendar_service.move_event(
                event_id=payload.event_id,
                new_date=payload.new_date.isoformat(),
                new_time=payload.new_time.strftime("%H:%M"),
                duration_minutes=payload.duration_minutes,
                telegram_id=user_id,
            )
        except (
            CalendarInputError,
            CalendarAuthRequiredError,
            CalendarTokenRefreshError,
            CalendarIntegrationError,
            EventNotFoundError,
        ) as error:
            return self._describe_calendar_error(error)

        return (
            f"Событие «{event.title}» перенесено на "
            f"{payload.new_date.isoformat()} в {payload.new_time.strftime('%H:%M')}. "
            f"ID: {event.event_id}"
        )

    # --- Вспомогательное -------------------------------------------------

    @staticmethod
    def _validate(tool_name: str, schema: type, arguments: dict):
        try:
            return schema(**arguments)
        except ValidationError as error:
            raise ToolArgumentError(tool_name, error) from error

    @staticmethod
    def _describe_calendar_error(error: Exception) -> str:
        if isinstance(error, CalendarInputError):
            return f"Ошибка ввода: {error}"
        if isinstance(error, CalendarAuthRequiredError):
            return "Пользователь не авторизован в Google Calendar. Попроси пройти /login."
        if isinstance(error, CalendarTokenRefreshError):
            return "Не удалось обновить токен Google. Попроси пользователя пройти /login заново."
        if isinstance(error, EventNotFoundError):
            return (
                "Событие с таким ID не найдено — возможно, оно уже удалено. "
                "Вызови get_events, чтобы получить актуальные ID, не выдумывай их."
            )
        return "Google Calendar временно недоступен. Предложи попробовать позже."

    @staticmethod
    def _format_event(event: CalendarEvent) -> str:
        start, end = event.start, event.end
        if isinstance(start, datetime) and isinstance(end, datetime):
            when = (
                f"{start.strftime('%Y-%m-%d %H:%M')}–{end.strftime('%H:%M')}"
                if start.date() == end.date()
                else f"{start.strftime('%Y-%m-%d %H:%M')} – {end.strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            when = f"{start.isoformat()} (весь день)"
        return f"- «{event.title}» {when} (ID: {event.event_id})"

    @staticmethod
    def _format_slot(start: datetime, end: datetime) -> str:
        if start.date() == end.date():
            return f"- {start.strftime('%Y-%m-%d %H:%M')}–{end.strftime('%H:%M')}"
        return (
            f"- {start.strftime('%Y-%m-%d %H:%M')} – "
            f"{end.strftime('%Y-%m-%d %H:%M')}"
        )