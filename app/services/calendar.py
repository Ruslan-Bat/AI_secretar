"""Проверяет строгий формат команд и вызывает независимый CalendarGateway."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone, tzinfo, time
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

_SLOT_MINUTES = 30
_MAX_RANGE_DAYS = 31
_MAX_EVENTS_PER_QUERY = 2500
_WORK_DAY_START = time(8, 0)
_WORK_DAY_END = time(22, 0)

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
        time_zone = await self._resolve_time_zone(telegram_id)

        logger.debug(
            "Calendar list requested by telegram_id=%s refresh_token_present=%s",
            telegram_id,
            bool(user_credentials.refresh_token),
        )
        
        events = await self._gateway.list_upcoming(
            time_min=now.astimezone(timezone.utc),
            limit=self._max_results,
            time_zone=str(time_zone),
            user_credentials=user_credentials,
        )
        return [self._localize_event(event, time_zone) for event in events]

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
        event = await self._gateway.create_event(
            title=title,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            time_zone=str(time_zone),
            user_credentials=user_credentials,
        )
        return self._localize_event(event, time_zone)

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
        events, _, _, _, _ = await self._load_range(
            start_day_offset, end_day_offset, telegram_id
        )
        return events

    async def get_free_slots(
        self,
        start_day_offset: int = 0,
        end_day_offset: int = 1,
        telegram_id: int | None = None,
        min_duration_minutes: int = _SLOT_MINUTES,
    ) -> list[tuple[datetime, datetime]]:
        """Возвращает непрерывные свободные интервалы в рабочих часах.

        Прошедшее время не предлагается, события «на весь день»
        не считаются занятостью.
        """
        if min_duration_minutes < 1:
            raise CalendarInputError("Минимальная длительность должна быть больше нуля")

        events, time_zone, now, range_start, range_end = await self._load_range(
            start_day_offset, end_day_offset, telegram_id
        )

        busy: list[tuple[datetime, datetime]] = []
        for event in events:
            start, end, is_all_day = self._event_bounds(event, time_zone)
            if is_all_day:
                continue
            busy.append((start, end))

        slot_start = max(range_start, self._ceil_to_slot(now))
        free: list[tuple[datetime, datetime]] = []
        while slot_start < range_end:
            slot_end = slot_start + timedelta(minutes=_SLOT_MINUTES)
            if self._is_working_time(slot_start, time_zone) and not any(
                start < slot_end and end > slot_start for start, end in busy
            ):
                if free and free[-1][1] == slot_start:
                    free[-1] = (free[-1][0], slot_end)
                else:
                    free.append((slot_start, slot_end))
            slot_start = slot_end

        minimum = timedelta(minutes=min_duration_minutes)
        return [(start, end) for start, end in free if end - start >= minimum]

    @staticmethod
    def _ceil_to_slot(moment: datetime) -> datetime:
        moment = moment.replace(second=0, microsecond=0)
        remainder = moment.minute % _SLOT_MINUTES
        if remainder:
            moment += timedelta(minutes=_SLOT_MINUTES - remainder)
        return moment

    @staticmethod
    def _is_working_time(slot_start: datetime, time_zone: tzinfo) -> bool:
        local = slot_start.astimezone(time_zone).time()
        return _WORK_DAY_START <= local < _WORK_DAY_END

    async def move_event(
        self,
        event_id: str,
        new_date: str,
        new_time: str,
        duration_minutes: int,
        telegram_id: int,
    ) -> CalendarEvent:
        """Переносит событие, сохраняя название и остальные поля."""
        if not event_id or any(character.isspace() for character in event_id):
            raise CalendarInputError("Формат: EVENT_ID ГГГГ-ММ-ДД ЧЧ:ММ МИНУТЫ")
        if len(event_id) > 1024:
            raise CalendarInputError("Некорректный EVENT_ID")
        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
            raise CalendarInputError("Длительность должна быть числом минут")
        if not 1 <= duration_minutes <= 1440:
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

        today = self._now_in(time_zone).date()
        start_offset = (new_start.date() - today).days
        end_offset = ((new_end - timedelta(microseconds=1)).date() - today).days
        events = await self.get_events(start_offset, end_offset, telegram_id)


        user_credentials = await self._get_user_credentials(telegram_id)
        event = await self._gateway.update_event(
            event_id,
            start=new_start,
            end=new_end,
            time_zone=str(time_zone),
            user_credentials=user_credentials,
        )
        return self._localize_event(event, time_zone)

    async def get_time_zone(self, telegram_id: int) -> str:
        """Возвращает пояс, используемый для ввода и вывода времени."""
        return str(await self._resolve_time_zone(telegram_id))

    async def set_time_zone(self, telegram_id: int, time_zone: str) -> str:
        if self._auth_service is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")
        return await self._auth_service.set_user_time_zone(telegram_id, time_zone)

    @staticmethod
    def _localize_event(event: CalendarEvent, time_zone: tzinfo) -> CalendarEvent:
        """Сохраняет момент события, меняет только пояс представления."""
        start, end = event.start, event.end
        if isinstance(start, datetime):
            if start.tzinfo is None:
                start = start.replace(tzinfo=time_zone)
            start = start.astimezone(time_zone)
        if isinstance(end, datetime):
            if end.tzinfo is None:
                end = end.replace(tzinfo=time_zone)
            end = end.astimezone(time_zone)
        return replace(event, start=start, end=end)

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


    def _now_in(self, time_zone: tzinfo) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(time_zone)

    @staticmethod
    def _day_range(
        today: date, start_day_offset: int, end_day_offset: int, time_zone: tzinfo
    ) -> tuple[datetime, datetime]:
        range_start = datetime.combine(
            today + timedelta(days=start_day_offset), datetime.min.time(), tzinfo=time_zone
        )
        range_end = datetime.combine(
            today + timedelta(days=end_day_offset + 1), datetime.min.time(), tzinfo=time_zone
        )
        return range_start, range_end

    @staticmethod
    def _event_bounds(
        event: CalendarEvent, time_zone: tzinfo
    ) -> tuple[datetime, datetime, bool]:
        """Приводит границы события к aware datetime.

        Третий элемент — признак события «на весь день»: у таких событий
        Google отдаёт date вместо dateTime, и они не занимают время
        в календаре, поэтому не должны учитываться как занятость.
        """
        is_all_day = not isinstance(event.start, datetime)
        start, end = event.start, event.end
        if not isinstance(start, datetime):
            start = datetime.combine(start, datetime.min.time(), tzinfo=time_zone)
        elif start.tzinfo is None:
            start = start.replace(tzinfo=time_zone)
        if not isinstance(end, datetime):
            end = datetime.combine(end, datetime.min.time(), tzinfo=time_zone)
        elif end.tzinfo is None:
            end = end.replace(tzinfo=time_zone)
        return start, end, is_all_day

    def _validate_range(self, start_day_offset: int, end_day_offset: int) -> None:
        if start_day_offset > end_day_offset:
            raise CalendarInputError("Начало диапазона не может быть позже конца")
        if end_day_offset - start_day_offset + 1 > _MAX_RANGE_DAYS:
            raise CalendarInputError(
                f"Диапазон не может превышать {_MAX_RANGE_DAYS} дней"
            )

    async def _load_range(
        self, start_day_offset: int, end_day_offset: int, telegram_id: int | None
    ) -> tuple[list[CalendarEvent], tzinfo, datetime, datetime, datetime]:
        """Единая точка загрузки диапазона: события, таймзона, now и границы."""
        self._validate_range(start_day_offset, end_day_offset)
        if telegram_id is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")

        time_zone = await self._resolve_time_zone(telegram_id)
        now = self._now_in(time_zone)
        range_start, range_end = self._day_range(
            now.date(), start_day_offset, end_day_offset, time_zone
        )

        user_credentials = await self._get_user_credentials(telegram_id)
        events = await self._gateway.list_upcoming(
            time_min=range_start.astimezone(timezone.utc),
            limit=_MAX_EVENTS_PER_QUERY,
            time_zone=str(time_zone),
            user_credentials=user_credentials,
        )

        result: list[CalendarEvent] = []
        for event in events:
            start, end, _ = self._event_bounds(event, time_zone)
            if start < range_end and end > range_start:
                result.append(self._localize_event(event, time_zone))
        return result, time_zone, now, range_start, range_end
