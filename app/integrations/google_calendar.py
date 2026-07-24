"""Адаптер Google Calendar API с авторизацией через сервисную учётную запись."""

import asyncio
import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build

from app.core.calendar_exceptions import CalendarIntegrationError
from app.domain.calendar_event import CalendarEvent


logger = logging.getLogger(__name__)
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


class GoogleCalendarGateway:
    """Выполняет блокирующие вызовы Google-клиента вне цикла asyncio."""

    def __init__(
        self,
        *,
        credentials_file: Path,
        calendar_id: str,
        time_zone: str,
    ) -> None:
        self._credentials_file = credentials_file
        self._calendar_id = calendar_id
        self._time_zone_name = time_zone
        self._time_zone = ZoneInfo(time_zone)
        self._service: Resource | None = None
        self._service_lock = threading.Lock()
        self._request_lock = threading.Lock()

    def _get_service(self) -> Resource:
        # Учётные данные загружаются только при первой календарной команде.
        with self._service_lock:
            if self._service is None:
                credentials = service_account.Credentials.from_service_account_file(
                    str(self._credentials_file),
                    scopes=[CALENDAR_SCOPE],
                )
                self._service = build(
                    "calendar",
                    "v3",
                    credentials=credentials,
                    cache_discovery=False,
                )
            return self._service

    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
    ) -> list[CalendarEvent]:
        try:
            # Официальный клиент Google синхронный, поэтому не блокируем цикл событий.
            return await asyncio.to_thread(self._list_upcoming, time_min, limit)
        except Exception as error:
            logger.warning("Google Calendar list failed (%s)", type(error).__name__)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from None

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
    ) -> CalendarEvent:
        try:
            return await asyncio.to_thread(self._create_event, title, start, end)
        except Exception as error:
            logger.warning("Google Calendar insert failed (%s)", type(error).__name__)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from None

    async def delete_event(self, event_id: str) -> None:
        try:
            await asyncio.to_thread(self._delete_event, event_id)
        except Exception as error:
            logger.warning("Google Calendar delete failed (%s)", type(error).__name__)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from None

    def _list_upcoming(self, time_min: datetime, limit: int) -> list[CalendarEvent]:
        with self._request_lock:
            response = (
                self._get_service()
                .events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=time_min.isoformat(),
                    maxResults=limit,
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone=self._time_zone_name,
                )
                .execute()
            )

        events: list[CalendarEvent] = []
        for item in response.get("items", []):
            try:
                events.append(self._from_google_event(item))
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipped malformed Google Calendar event")
        return events

    def _create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
    ) -> CalendarEvent:
        body = {
            "summary": title,
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": self._time_zone_name,
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": self._time_zone_name,
            },
        }
        with self._request_lock:
            result = (
                self._get_service()
                .events()
                .insert(calendarId=self._calendar_id, body=body)
                .execute()
            )
        return self._from_google_event(result)

    def _delete_event(self, event_id: str) -> None:
        with self._request_lock:
            (
                self._get_service()
                .events()
                .delete(calendarId=self._calendar_id, eventId=event_id)
                .execute()
            )

    def _from_google_event(self, item: dict[str, Any]) -> CalendarEvent:
        return CalendarEvent(
            event_id=item["id"],
            title=item.get("summary") or "Без названия",
            start=self._parse_event_point(item["start"]),
            end=self._parse_event_point(item["end"]),
            html_link=item.get("htmlLink"),
        )

    def _parse_event_point(self, value: dict[str, str]) -> datetime | date:
        date_time = value.get("dateTime")
        if date_time:
            parsed = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=self._time_zone)
            return parsed
        date_value = value.get("date")
        if date_value:
            return date.fromisoformat(date_value)
        raise ValueError("Calendar event point has neither dateTime nor date")
