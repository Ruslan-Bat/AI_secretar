from datetime import datetime, timezone

import pytest

from app.core.calendar_exceptions import CalendarInputError
from app.domain.calendar_event import CalendarEvent
from app.services.calendar import CalendarService


class FakeCalendarGateway:
    def __init__(self) -> None:
        self.events: list[CalendarEvent] = []
        self.list_call: tuple[datetime, int] | None = None
        self.created: tuple[str, datetime, datetime] | None = None
        self.deleted_event_id: str | None = None

    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
    ) -> list[CalendarEvent]:
        self.list_call = (time_min, limit)
        return self.events

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
    ) -> CalendarEvent:
        self.created = (title, start, end)
        return CalendarEvent(
            event_id="google-event-id",
            title=title,
            start=start,
            end=end,
        )

    async def delete_event(self, event_id: str) -> None:
        self.deleted_event_id = event_id


def make_service(gateway: FakeCalendarGateway) -> CalendarService:
    return CalendarService(
        gateway,
        time_zone="Europe/Moscow",
        max_results=5,
        clock=lambda: datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_lists_upcoming_events_with_limit() -> None:
    gateway = FakeCalendarGateway()
    expected = CalendarEvent(
        event_id="event-1",
        title="Встреча",
        start=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
    )
    gateway.events = [expected]

    result = await make_service(gateway).list_upcoming()

    assert result == [expected]
    assert gateway.list_call == (
        datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
        5,
    )


@pytest.mark.asyncio
async def test_creates_event_from_deterministic_command() -> None:
    gateway = FakeCalendarGateway()

    result = await make_service(gateway).create_from_text(
        "2026-07-20 14:30 60 Рабочая встреча"
    )

    assert result.event_id == "google-event-id"
    assert gateway.created is not None
    title, start, end = gateway.created
    assert title == "Рабочая встреча"
    assert start.isoformat() == "2026-07-20T14:30:00+03:00"
    assert end.isoformat() == "2026-07-20T15:30:00+03:00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        None,
        "2026-07-20",
        "20.07.2026 14:30 60 Встреча",
        "2026-07-20 14:30 zero Встреча",
        "2026-07-20 14:30 0 Встреча",
    ],
)
async def test_rejects_invalid_add_event_arguments(arguments: str | None) -> None:
    with pytest.raises(CalendarInputError):
        await make_service(FakeCalendarGateway()).create_from_text(arguments)


@pytest.mark.asyncio
async def test_deletes_event_by_id() -> None:
    gateway = FakeCalendarGateway()

    await make_service(gateway).delete_from_text("event-id-123")

    assert gateway.deleted_event_id == "event-id-123"


@pytest.mark.asyncio
async def test_rejects_invalid_delete_event_id() -> None:
    with pytest.raises(CalendarInputError):
        await make_service(FakeCalendarGateway()).delete_from_text("two ids")
