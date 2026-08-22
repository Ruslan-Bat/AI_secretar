from datetime import date, datetime
from typing import Any

import pytest

from app.integrations.google_calendar import GoogleCalendarGateway

from app.core.calendar_exceptions import CalendarIntegrationError


class FakeRequest:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    def execute(self) -> Any:
        if self._error:
            raise self._error
        return self._response


class FakeEventsResource:
    def __init__(self) -> None:
        self.list_arguments: dict[str, Any] | None = None
        self.insert_arguments: dict[str, Any] | None = None
        self.delete_arguments: dict[str, Any] | None = None

    def list(self, **arguments: Any) -> FakeRequest:
        self.list_arguments = arguments
        return FakeRequest(
            {
                "items": [
                    {
                        "id": "timed-id",
                        "summary": "Встреча",
                        "start": {"dateTime": "2026-07-20T14:30:00+03:00"},
                        "end": {"dateTime": "2026-07-20T15:30:00+03:00"},
                    },
                    {
                        "id": "all-day-id",
                        "summary": "Выходной",
                        "start": {"date": "2026-07-21"},
                        "end": {"date": "2026-07-22"},
                    },
                ]
            }
        )

    def insert(self, **arguments: Any) -> FakeRequest:
        self.insert_arguments = arguments
        body = arguments["body"]
        return FakeRequest(
            {
                "id": "created-id",
                "summary": body["summary"],
                "start": body["start"],
                "end": body["end"],
                "htmlLink": "https://calendar.google.test/event",
            }
        )

    def delete(self, **arguments: Any) -> FakeRequest:
        self.delete_arguments = arguments
        return FakeRequest()


class FakeGoogleService:
    def __init__(
            self, 
            events: FakeEventsResource,
            calendars: FakeEventsResource | None = None
            ) -> None:
        self._events = events
        self._calendars = calendars if calendars is not None else FakeEventsResource()

    def events(self) -> FakeEventsResource:
        return self._events

    def calendars(self) -> FakeEventsResource:
        return self._calendars


def make_gateway() -> tuple[GoogleCalendarGateway, FakeEventsResource]:
    events = FakeEventsResource()
    gateway = GoogleCalendarGateway(time_zone="Europe/Moscow")
    gateway._get_service = lambda user_credentials=None: FakeGoogleService(events)  # type: ignore[assignment]
    return gateway, events


class FakeCalendarsResource:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.get_arguments: dict[str, Any] | None = None
        self._response = response if response is not None else {"timeZone": "Europe/Moscow"}
        self._error = error

    def get(self, **arguments: Any) -> FakeRequest:
        self.get_arguments = arguments
        return FakeRequest(self._response, error=self._error)


def make_gateway_for_timezone(
    response: Any = None, error: Exception | None = None
) -> tuple[GoogleCalendarGateway, FakeCalendarsResource]:
    events = FakeEventsResource()
    calendars = FakeCalendarsResource(response=response, error=error)
    gateway = GoogleCalendarGateway(time_zone="Europe/Moscow")
    gateway._get_service = lambda user_credentials=None: FakeGoogleService(events, calendars)  # type: ignore[assignment]
    return gateway, calendars


@pytest.mark.asyncio
async def test_maps_google_events_without_network() -> None:
    gateway, events_resource = make_gateway()

    events = await gateway.list_upcoming(
        time_min=datetime.fromisoformat("2026-07-19T10:00:00+00:00"),
        limit=10,
        user_credentials="credentials",
    )

    assert [event.event_id for event in events] == ["timed-id", "all-day-id"]
    assert isinstance(events[0].start, datetime)
    assert events[1].start == date(2026, 7, 21)
    assert events_resource.list_arguments == {
        "calendarId": "primary",
        "timeMin": "2026-07-19T10:00:00+00:00",
        "maxResults": 10,
        "singleEvents": True,
        "orderBy": "startTime",
        "timeZone": "Europe/Moscow",
    }



@pytest.mark.asyncio
async def test_creates_and_deletes_google_event_without_network() -> None:
    gateway, events_resource = make_gateway()
    start = datetime.fromisoformat("2026-07-20T14:30:00+03:00")
    end = datetime.fromisoformat("2026-07-20T15:30:00+03:00")

    created = await gateway.create_event(title="Встреча", start=start, end=end, user_credentials="credentials")
    await gateway.delete_event(created.event_id, user_credentials="credentials")

    assert created.event_id == "created-id"
    assert events_resource.insert_arguments == {
        "calendarId": "primary",
        "body": {
            "summary": "Встреча",
            "start": {
                "dateTime": "2026-07-20T14:30:00+03:00",
                "timeZone": "Europe/Moscow",
            },
            "end": {
                "dateTime": "2026-07-20T15:30:00+03:00",
                "timeZone": "Europe/Moscow",
            },
        },
    }
    assert events_resource.delete_arguments == {
        "calendarId": "primary",
        "eventId": "created-id",
    }


@pytest.mark.asyncio
async def test_get_primary_calendar_timezone_returns_value_without_network() -> None:
    gateway, calendars_resource = make_gateway_for_timezone(
        response={"timeZone": "Asia/Almaty"}
    )

    time_zone = await gateway.get_primary_calendar_timezone(user_credentials="credentials")

    assert time_zone == "Asia/Almaty"
    assert calendars_resource.get_arguments == {"calendarId": "primary"}


@pytest.mark.asyncio
async def test_get_primary_calendar_timezone_raises_when_field_missing() -> None:
    gateway, _ = make_gateway_for_timezone(response={})

    with pytest.raises(CalendarIntegrationError):
        await gateway.get_primary_calendar_timezone(user_credentials="credentials")


@pytest.mark.asyncio
async def test_get_primary_calendar_timezone_wraps_google_api_errors() -> None:
    gateway, _ = make_gateway_for_timezone(error=RuntimeError("Google is down"))

    with pytest.raises(CalendarIntegrationError):
        await gateway.get_primary_calendar_timezone(user_credentials="credentials")


def test_gateway_still_satisfies_calendar_gateway_protocol() -> None:
    from app.integrations.calendar import CalendarGateway

    gateway = GoogleCalendarGateway(time_zone="Europe/Moscow")

    assert isinstance(gateway, CalendarGateway)
