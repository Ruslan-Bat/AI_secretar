from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from typing import Any

import pytest

from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
)
from app.domain.calendar_event import CalendarEvent
from app.services.calendar import CalendarService


class FakeCalendarGateway:
    def __init__(self) -> None:
        self.events: list[CalendarEvent] = []
        self.list_call: tuple[datetime, int] | None = None
        self.created: tuple[str, datetime, datetime] | None = None
        self.deleted_event_id: str | None = None
        self.user_credentials: Any | None = None
        self.time_zone_requested: bool = False

    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
        user_credentials: Any | None = None,
    ) -> list[CalendarEvent]:
        self.list_call = (time_min, limit)
        return self.events

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        user_credentials: Any | None = None,
    ) -> CalendarEvent:
        self.created = (title, start, end)
        self.user_credentials = user_credentials
        return CalendarEvent(
            event_id="google-event-id",
            title=title,
            start=start,
            end=end,
        )

    async def delete_event(self, event_id: str, user_credentials: Any | None = None) -> None:
        self.deleted_event_id = event_id
        self.user_credentials = user_credentials

    async def get_primary_calendar_timezone(self, user_credentials: Any | None = None) -> str:
        self.time_zone_requested = True
        self.user_credentials = user_credentials
        return "Europe/Moscow"


def make_service(
    gateway: FakeCalendarGateway,
    auth_service: Any | None = None,
) -> CalendarService:
    return CalendarService(
        gateway,
        time_zone="Europe/Moscow",
        max_results=5,
        clock=lambda: datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
        auth_service=auth_service,
    )

def _fake_oauth_credentials(refresh_token: str = "fake-refresh-token") -> SimpleNamespace:
    """Минимальная замена объекта google.oauth2.credentials.Credentials
    для тестов CalendarService.list_upcoming — несёт единственный
    атрибут, реально используемый сервисом (отладочное логирование)."""
    return SimpleNamespace(refresh_token=refresh_token)

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

    fake_credentials = _fake_oauth_credentials()
    auth_service = SimpleNamespace(get_oauth_credentials=AsyncMock(return_value=fake_credentials))

    result = await make_service(gateway, auth_service=auth_service).list_upcoming(telegram_id=123)

    assert result == [expected]
    assert gateway.list_call == (
        datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
        5,
        fake_credentials,
    )

@pytest.mark.asyncio
async def test_lists_upcoming_events_with_user_credentials() -> None:
    gateway = FakeCalendarGateway()
    expected = CalendarEvent(
        event_id="event-1",
        title="Встреча",
        start=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
    )
    gateway.events = [expected]

    fake_credentials = _fake_oauth_credentials()
    auth_service = SimpleNamespace(get_oauth_credentials=AsyncMock(return_value=fake_credentials))

    result = await make_service(gateway, auth_service=auth_service).list_upcoming(telegram_id=123)

    assert result == [expected]
    assert gateway.list_call == (
        datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
        5,
        fake_credentials,
    )


@pytest.mark.asyncio
async def test_creates_event_from_deterministic_command() -> None:
    gateway = FakeCalendarGateway()
    auth_service = SimpleNamespace(
        get_oauth_credentials=AsyncMock(return_value="credentials"),
        get_user_time_zone=AsyncMock(return_value=None)
    )

    result = await make_service(gateway, auth_service=auth_service).create_from_text(
        "2026-07-20 14:30 60 Рабочая встреча",
        telegram_id=123,
    )

    assert result.event_id == "google-event-id"
    assert gateway.created is not None
    title, start, end = gateway.created
    assert title == "Рабочая встреча"
    assert start.isoformat() == "2026-07-20T14:30:00+03:00"
    assert end.isoformat() == "2026-07-20T15:30:00+03:00"
    assert gateway.user_credentials == "credentials"



@pytest.mark.asyncio
async def test_deletes_event_by_id() -> None:
    gateway = FakeCalendarGateway()
    auth_service = SimpleNamespace(get_oauth_credentials=AsyncMock(return_value="credentials"))

    await make_service(gateway, auth_service=auth_service).delete_from_text(
        "event-id-123",
        telegram_id=123,
    )

    assert gateway.deleted_event_id == "event-id-123"
    assert gateway.user_credentials == "credentials"


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
    auth_service = SimpleNamespace(get_oauth_credentials=AsyncMock(return_value="credentials"))
    with pytest.raises(CalendarInputError):
        await make_service(FakeCalendarGateway(), auth_service=auth_service).create_from_text(
            arguments, telegram_id=123
        )


@pytest.mark.asyncio
async def test_rejects_invalid_delete_event_id() -> None:
    auth_service = SimpleNamespace(get_oauth_credentials=AsyncMock(return_value="credentials"))
    with pytest.raises(CalendarInputError):
        await make_service(FakeCalendarGateway(), auth_service=auth_service).delete_from_text(
            "two ids", telegram_id=123
        )


@pytest.mark.asyncio
async def test_raises_auth_required_when_auth_service_missing_for_add_event() -> None:
    """Ранее назывался test_requires_telegram_id_for_add_event — но
    telegram_id обязателен по сигнатуре, реально этот тест проверяет
    отсутствие auth_service (make_service(gateway) передаёт auth_service=None)."""
    gateway = FakeCalendarGateway()
    with pytest.raises(CalendarAuthRequiredError):
        await make_service(gateway).create_from_text(
            "2026-07-20 14:30 60 Встреча", telegram_id=123
        )


@pytest.mark.asyncio
async def test_raises_auth_required_when_auth_service_missing_for_delete_event() -> None:
    """Ранее назывался test_requires_telegram_id_for_delete_event — см.
    комментарий выше, аналогичная причина переименования."""
    gateway = FakeCalendarGateway()
    with pytest.raises(CalendarAuthRequiredError):
        await make_service(gateway).delete_from_text("event-id-123", telegram_id=123)