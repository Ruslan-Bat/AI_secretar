"""Адаптер Google Calendar API с авторизацией через OAuth пользователя."""

import asyncio
import logging
import threading
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.calendar_exceptions import CalendarIntegrationError, EventNotFoundError
from app.domain.calendar_event import CalendarEvent


logger = logging.getLogger(__name__)


class GoogleCalendarGateway:
    """Выполняет блокирующие вызовы Google-клиента вне цикла asyncio."""

    def __init__(
        self,
        *,
        time_zone: str,
    ) -> None:
        self._time_zone_name = time_zone
        self._time_zone = ZoneInfo(time_zone)

    def _get_service(self, user_credentials: OAuthCredentials | None = None) -> Any:
        if user_credentials is None:
            raise ValueError("OAuth credentials are required to access Google Calendar")
        if not isinstance(user_credentials, OAuthCredentials):
            raise TypeError(
                f"GoogleCalendarGateway expected OAuthCredentials, got {type(user_credentials).__name__}"
            )

        return build(
            "calendar",
            "v3",
            credentials=user_credentials,
            cache_discovery=False,
        )

    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
        time_zone=None,
        user_credentials: OAuthCredentials | None = None,
    ) -> list[CalendarEvent]:
        try:
            return await asyncio.to_thread(self._list_upcoming, time_min, limit, time_zone, user_credentials)
        except Exception as error:
            logger.exception("Google Calendar list failed: %s", error)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from error

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        time_zone=None,
        user_credentials: OAuthCredentials | None = None,
    ) -> CalendarEvent:
        try:
            return await asyncio.to_thread(self._create_event, title, start, end, time_zone, user_credentials)
        except Exception as error:
            logger.exception("Google Calendar insert failed: %s", error)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from error

    async def delete_event(self, event_id: str, user_credentials: OAuthCredentials | None = None) -> None:
        try:
            await asyncio.to_thread(self._delete_event, event_id, user_credentials)
        except EventNotFoundError:
            raise
        except Exception as error:
            logger.exception("Google Calendar delete failed: %s", error)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from error

    async def update_event(
        self,
        event_id: str,
        *,
        start: datetime,
        end: datetime,
        time_zone=None,
        user_credentials: OAuthCredentials | None = None,
    ) -> CalendarEvent:
        try:
            return await asyncio.to_thread(
                self._update_event, event_id, start, end, time_zone, user_credentials
            )
        except EventNotFoundError:
            raise
        except Exception as error:
            logger.exception("Google Calendar patch failed: %s", error)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from error

    def _update_event(
        self,
        event_id: str,
        start: datetime,
        end: datetime,
        time_zone=None,
        user_credentials: OAuthCredentials | None = None,
    ) -> CalendarEvent:
        zone_name = time_zone or self._time_zone_name
        body = {
            "start": {"dateTime": start.isoformat(), "timeZone": zone_name},
            "end": {"dateTime": end.isoformat(), "timeZone": zone_name},
        }
        try:
            result = (
                self._get_service(user_credentials)
                .events()
                .patch(
                    calendarId=self._get_calendar_id(user_credentials),
                    eventId=event_id,
                    body=body,
                )
                .execute()
            )
        except HttpError as error:
            if error.resp.status in (404, 410):
                raise EventNotFoundError("Событие не найдено в Google Календаре")
            raise
        return self._from_google_event(result)

    async def get_primary_calendar_timezone(self, user_credentials: OAuthCredentials | None = None) -> str:
        try:
            return await asyncio.to_thread(self._get_primary_calendar_timezone, user_credentials)
        except Exception as error:
            logger.exception("Google Calendar timezone fetch failed: %s", error)
            raise CalendarIntegrationError(
                "Google Calendar is temporarily unavailable"
            ) from error

    def _get_primary_calendar_timezone(self, user_credentials: OAuthCredentials | None = None) -> str:
        result = (
            self._get_service(user_credentials)
            .calendars()
            .get(calendarId=self._get_calendar_id(user_credentials))
            .execute()
        )
        time_zone = result.get("timeZone")
        if not time_zone:
            raise ValueError("Google Calendar response has no timeZone field")
        return time_zone

    def _get_calendar_id(self, user_credentials: OAuthCredentials | None = None) -> str:
        if user_credentials is None:
            raise ValueError("OAuth credentials are required to access Google Calendar")
        return "primary"

    def _list_upcoming(
        self,
        time_min: datetime,
        limit: int,
        time_zone=None,
        user_credentials: OAuthCredentials | None = None,
    ) -> list[CalendarEvent]:
        zone_name = time_zone or self._time_zone_name
        response = (
            self._get_service(user_credentials)
            .events()
            .list(
                calendarId=self._get_calendar_id(user_credentials),
                timeMin=time_min.isoformat(),
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
                timeZone=zone_name,
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
        time_zone=None,
        user_credentials: OAuthCredentials | None = None,
    ) -> CalendarEvent:
        zone_name = time_zone or self._time_zone_name
        body = {
            "summary": title,
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": zone_name,
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": zone_name,
            },
        }
        result = (
            self._get_service(user_credentials)
            .events()
            .insert(calendarId=self._get_calendar_id(user_credentials), body=body)
            .execute()
        )
        return self._from_google_event(result)

    def _delete_event(self, event_id: str, user_credentials: OAuthCredentials | None = None) -> None:
        try:
            (
                self._get_service(user_credentials)
                .events()
                .delete(calendarId=self._get_calendar_id(user_credentials), eventId=event_id)
                .execute()
            )
        except HttpError as error:
            # 410 Gone (Уже удалено) или 404 Not Found (Не найдено)
            if error.resp.status in (404, 410):
                logger.info(f"Событие {event_id} уже удалено из Google Календаря (статус {error.resp.status})")
                raise EventNotFoundError(f"Событие не найдено в Google Календаре")
            
            # Если возникла другая ошибка (например, 401 Нет прав, 403 Лимит запросов), пробрасываем её дальше
            logger.error(f"Ошибка при удалении события {event_id}: {error}")
            raise

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
