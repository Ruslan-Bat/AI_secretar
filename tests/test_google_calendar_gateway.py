from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.integrations.google_calendar import GoogleCalendarGateway


class FakeRequest:
    def __init__(self, response: Any = None) -> None:
        self._response = response

    def execute(self) -> Any:
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
    def __init__(self, events: FakeEventsResource) -> None:
        self._events = events

    def events(self) -> FakeEventsResource:
        return self._events


def make_gateway() -> tuple[GoogleCalendarGateway, FakeEventsResource]:
    events = FakeEventsResource()
    gateway = GoogleCalendarGateway(
        credentials_file=Path("unused-service-account.json"),
        calendar_id="calendar@example.com",
        time_zone="Europe/Moscow",
    )
    gateway._service = FakeGoogleService(events)  # type: ignore[assignment]
    return gateway, events


@pytest.mark.asyncio
async def test_maps_google_events_without_network() -> None:
    gateway, events_resource = make_gateway()

    events = await gateway.list_upcoming(
        time_min=datetime.fromisoformat("2026-07-19T10:00:00+00:00"),
        limit=10,
    )

    assert [event.event_id for event in events] == ["timed-id", "all-day-id"]
    assert isinstance(events[0].start, datetime)
    assert events[1].start == date(2026, 7, 21)
    assert events_resource.list_arguments == {
        "calendarId": "calendar@example.com",
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

    created = await gateway.create_event(title="Встреча", start=start, end=end)
    await gateway.delete_event(created.event_id)

    assert created.event_id == "created-id"
    assert events_resource.insert_arguments == {
        "calendarId": "calendar@example.com",
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
        "calendarId": "calendar@example.com",
        "eventId": "created-id",
    }
