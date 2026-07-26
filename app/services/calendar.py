"""Проверяет строгий формат команд и вызывает независимый CalendarGateway."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import logging
from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
)
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
        self._time_zone = ZoneInfo(time_zone)
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
            user_credentials.refresh_token,
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
        try:
            start = datetime.strptime(
                f"{date_text} {time_text}",
                "%Y-%m-%d %H:%M",
            ).replace(tzinfo=self._time_zone)
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
