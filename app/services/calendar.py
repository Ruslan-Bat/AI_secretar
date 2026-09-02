"""Проверяет строгий формат команд и вызывает независимый CalendarGateway."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

import logging
from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
)
from app.core.time_zone import parse_time_zone
from app.domain.calendar_event import CalendarEvent
from app.integrations.calendar import CalendarGateway
from app.services.google_auth import GoogleAuthService

logger = logging.getLogger(__name__)
    
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CalendarService:
    def __init__(
        self,
        gateway: CalendarGateway,
        *,
        time_zone: str,
        max_results: int = 10,
        clock: Clock = utc_now,
        auth_service: GoogleAuthService | None = None,
    ) -> None:
        self._gateway = gateway
        self._default_time_zone = ZoneInfo(time_zone)
        self._max_results = max_results
        self._clock = clock
        self._auth_service = auth_service

    async def list_upcoming(self, telegram_id: int | None = None) -> list[CalendarEvent]:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if telegram_id is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")

        if self._auth_service is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")

        user_credentials = await self._auth_service.get_oauth_credentials(telegram_id)

        logger.debug(
            "Calendar list requested by telegram_id=%s refresh_token=%s",
            telegram_id,
            "refresh_token_present=%s", bool(user_credentials.refresh_token),
        )
        
        return await self._gateway.list_upcoming(
            time_min=now.astimezone(timezone.utc),
            limit=self._max_results,
            user_credentials=user_credentials,
        )

    async def _get_user_credentials(self, telegram_id: int) -> Any | None:
        if self._auth_service is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")
        return await self._auth_service.get_oauth_credentials(telegram_id)

    async def create_from_text(self, arguments: str | None, telegram_id: int) -> CalendarEvent:
        if not arguments:
            raise CalendarInputError(
                "Формат: /add_event ГГГГ-ММ-ДД ЧЧ:ММ МИНУТЫ НАЗВАНИЕ"
            )

        parts = arguments.strip().split(maxsplit=3)
        if len(parts) != 4:
            raise CalendarInputError(
                "Формат: /add_event ГГГГ-ММ-ДД ЧЧ:ММ МИНУТЫ НАЗВАНИЕ"
            )

        date_text, time_text, duration_text, title = parts
        time_zone = await self._resolve_time_zone(telegram_id)
        try:
            start = datetime.strptime(
                f"{date_text} {time_text}",
                "%Y-%m-%d %H:%M",
            ).replace(tzinfo=time_zone)
        except ValueError:
            raise CalendarInputError(
                "Дата и время должны иметь формат ГГГГ-ММ-ДД ЧЧ:ММ"
            ) from None

        try:
            duration_minutes = int(duration_text)
        except ValueError:
            raise CalendarInputError("Длительность должна быть числом минут") from None

        if not 1 <= duration_minutes <= 1440:
            raise CalendarInputError("Длительность должна быть от 1 до 1440 минут")

        title = title.strip()
        if not title or len(title) > 200:
            raise CalendarInputError("Название должно содержать от 1 до 200 символов")

        user_credentials = await self._get_user_credentials(telegram_id)
        return await self._gateway.create_event(
            title=title,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            user_credentials=user_credentials,
        )

    async def delete_from_text(self, arguments: str | None, telegram_id: int) -> None:
        event_id = (arguments or "").strip()
        if not event_id or any(character.isspace() for character in event_id):
            raise CalendarInputError("Формат: /delete_event EVENT_ID")
        if len(event_id) > 1024:
            raise CalendarInputError("Некорректный EVENT_ID")
        user_credentials = await self._get_user_credentials(telegram_id)
        await self._gateway.delete_event(event_id, user_credentials=user_credentials)

    async def get_events(
        self,
        start_day_offset: int = 0,
        end_day_offset: int = 1,
        telegram_id: int | None = None,
    ) -> list[CalendarEvent]:
        """Возвращает события с начала первого до конца последнего дня."""
        if start_day_offset > end_day_offset:
            raise CalendarInputError("Начало диапазона не может быть позже конца")
        if telegram_id is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")

        time_zone = await self._resolve_time_zone(telegram_id)
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        today = now.astimezone(time_zone).date()
        range_start = datetime.combine(
            today + timedelta(days=start_day_offset),
            datetime.min.time(),
            tzinfo=time_zone,
        )
        range_end = datetime.combine(
            today + timedelta(days=end_day_offset + 1),
            datetime.min.time(),
            tzinfo=time_zone,
        )

        user_credentials = await self._get_user_credentials(telegram_id)
        events = await self._gateway.list_upcoming(
            time_min=range_start.astimezone(timezone.utc),
            limit=2500,
            user_credentials=user_credentials,
        )

        result: list[CalendarEvent] = []
        for event in events:
            start = event.start
            end = event.end
            if not isinstance(start, datetime):
                start = datetime.combine(start, datetime.min.time(), tzinfo=time_zone)
            elif start.tzinfo is None:
                start = start.replace(tzinfo=time_zone)
            if not isinstance(end, datetime):
                end = datetime.combine(end, datetime.min.time(), tzinfo=time_zone)
            elif end.tzinfo is None:
                end = end.replace(tzinfo=time_zone)
            if start < range_end and end > range_start:
                result.append(event)
        return result

    async def get_free_slots(
        self,
        start_day_offset: int = 0,
        end_day_offset: int = 1,
        telegram_id: int | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Возвращает свободные получасовые слоты в указанном диапазоне дней."""
        events = await self.get_events(start_day_offset, end_day_offset, telegram_id)
        if telegram_id is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")

        time_zone = await self._resolve_time_zone(telegram_id)
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        today = now.astimezone(time_zone).date()
        slot_start = datetime.combine(
            today + timedelta(days=start_day_offset),
            datetime.min.time(),
            tzinfo=time_zone,
        )
        range_end = datetime.combine(
            today + timedelta(days=end_day_offset + 1),
            datetime.min.time(),
            tzinfo=time_zone,
        )

        busy: list[tuple[datetime, datetime]] = []
        for event in events:
            start = event.start
            end = event.end
            if not isinstance(start, datetime):
                start = datetime.combine(start, datetime.min.time(), tzinfo=time_zone)
            elif start.tzinfo is None:
                start = start.replace(tzinfo=time_zone)
            if not isinstance(end, datetime):
                end = datetime.combine(end, datetime.min.time(), tzinfo=time_zone)
            elif end.tzinfo is None:
                end = end.replace(tzinfo=time_zone)
            busy.append((start, end))

        slots: list[tuple[datetime, datetime]] = []
        while slot_start < range_end:
            slot_end = slot_start + timedelta(minutes=30)
            if not any(start < slot_end and end > slot_start for start, end in busy):
                slots.append((slot_start, slot_end))
            slot_start = slot_end
        return slots

    async def move_event(
        self,
        event_id: str,
        new_date: str,
        new_time: str,
        duration_minutes: int,
        telegram_id: int,
    ) -> CalendarEvent:
        """Проверяет новое время, удаляет старое событие и создаёт новое."""
        if not event_id or any(character.isspace() for character in event_id):
            raise CalendarInputError(
                "Формат: EVENT_ID ГГГГ-ММ-ДД ЧЧ:ММ МИНУТЫ"
            )
        if len(event_id) > 1024:
            raise CalendarInputError("Некорректный EVENT_ID")
        if not isinstance(duration_minutes, int) or not 1 <= duration_minutes <= 1440:
            raise CalendarInputError("Длительность должна быть от 1 до 1440 минут")

        time_zone = await self._resolve_time_zone(telegram_id)
        try:
            new_start = datetime.strptime(
                f"{new_date} {new_time}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=time_zone)
        except ValueError:
            raise CalendarInputError(
                "Дата и время должны иметь формат ГГГГ-ММ-ДД ЧЧ:ММ"
            ) from None
        new_end = new_start + timedelta(minutes=duration_minutes)

        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        today = now.astimezone(time_zone).date()
        start_offset = (new_start.date() - today).days
        end_offset = ((new_end - timedelta(microseconds=1)).date() - today).days
        events = await self.get_events(start_offset, end_offset, telegram_id)

        for event in events:
            if event.event_id == event_id:
                continue
            start = event.start
            end = event.end
            if not isinstance(start, datetime):
                start = datetime.combine(start, datetime.min.time(), tzinfo=time_zone)
            elif start.tzinfo is None:
                start = start.replace(tzinfo=time_zone)
            if not isinstance(end, datetime):
                end = datetime.combine(end, datetime.min.time(), tzinfo=time_zone)
            elif end.tzinfo is None:
                end = end.replace(tzinfo=time_zone)
            if start < new_end and end > new_start:
                raise CalendarInputError("Выбранное время занято")

        user_credentials = await self._get_user_credentials(telegram_id)
        await self._gateway.delete_event(event_id, user_credentials=user_credentials)
        return await self._gateway.create_event(
            title="Перенесённое событие",
            start=new_start,
            end=new_end,
            user_credentials=user_credentials,
        )

    async def _resolve_time_zone(self, telegram_id: int | None) -> tzinfo:
        if telegram_id is None or self._auth_service is None:
            return self._default_time_zone
        try:
            stored = await self._auth_service.get_user_time_zone(telegram_id)
        except Exception:
            logger.warning(
                "Failed to resolve time zone for telegram_id=%s; using default",
                telegram_id, exc_info=True,
            )
            return self._default_time_zone
        return parse_time_zone(stored, self._default_time_zone)
