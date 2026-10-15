from datetime import date, datetime, timedelta, timezone
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

MOSCOW = timezone(timedelta(hours=3))
# Пятница, 10:00 по Москве (07:00 UTC) — «сейчас» во всех тестах ниже.
FIXED_NOW_UTC = datetime(2026, 7, 17, 7, 0, tzinfo=timezone.utc)

class FakeCalendarGateway:

    def __init__(self) -> None:
        self.events: list[CalendarEvent] = []
        self.list_call: tuple[datetime, int, Any] | None = (
            None  # Обновлена аннотация типов
        )
        self.created: tuple[str, datetime, datetime] | None = None
        self.deleted_event_id: str | None = None
        self.user_credentials: Any | None = None
        self.time_zone_requested: bool = False
        self.updated: tuple[str, datetime, datetime] | None = None
        self.request_time_zone: str | None = None

    async def list_upcoming(
        self,
        *,
        time_min: datetime,
        limit: int,
        time_zone: str | None = None,
        user_credentials: Any | None = None,
    ) -> list[CalendarEvent]:
        self.request_time_zone = time_zone
        self.list_call = (
            time_min,
            limit,
            user_credentials,
        )  # Теперь сохраняет 3 элемента
        self.user_credentials = user_credentials
        return self.events

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        time_zone: str | None = None,
        user_credentials: Any | None = None,
    ) -> CalendarEvent:
        self.request_time_zone = time_zone
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

    async def update_event(
        self,
        event_id: str,
        *,
        start: datetime,
        end: datetime,
        time_zone: str | None = None,
        user_credentials: Any | None = None,
    ) -> CalendarEvent:
        self.updated = (event_id, start, end)
        self.user_credentials = user_credentials
        return CalendarEvent(
            event_id=event_id,
            title="Исходное название",
            start=start,
            end=end,
        )

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

def make_service_at(
    gateway: FakeCalendarGateway,
    now_utc: datetime = FIXED_NOW_UTC,
    time_zone: str = "Europe/Moscow",
) -> CalendarService:
    auth_service = SimpleNamespace(
        get_oauth_credentials=AsyncMock(return_value=_fake_oauth_credentials()),
        get_user_time_zone=AsyncMock(return_value=time_zone),
    )
    return CalendarService(
        gateway,
        time_zone="Europe/Moscow",
        max_results=5,
        clock=lambda: now_utc,
        auth_service=auth_service,
    )

def event_at(
    event_id: str,
    start_local: datetime,
    duration_minutes: int = 60,
    title: str = "Событие",
) -> CalendarEvent:
    return CalendarEvent(
        event_id=event_id,
        title=title,
        start=start_local,
        end=start_local + timedelta(minutes=duration_minutes),
    )

def all_day_event(event_id: str, day: date, days: int = 1) -> CalendarEvent:
    """All-day событие: Google отдаёт date вместо datetime, конец эксклюзивный."""
    return CalendarEvent(
        event_id=event_id,
        title="Отпуск",
        start=day,
        end=day + timedelta(days=days),
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


@pytest.mark.asyncio
async def test_get_events_filters_by_requested_day_range() -> None:
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at("today", datetime(2026, 7, 17, 12, 0, tzinfo=MOSCOW)),
        event_at("tomorrow", datetime(2026, 7, 18, 12, 0, tzinfo=MOSCOW)),
        event_at("in-three-days", datetime(2026, 7, 20, 12, 0, tzinfo=MOSCOW)),
    ]

    result = await make_service_at(gateway).get_events(
        start_day_offset=0, end_day_offset=1, telegram_id=123
    )

    assert [event.event_id for event in result] == ["today", "tomorrow"]


@pytest.mark.asyncio
async def test_get_events_includes_all_day_events() -> None:
    """All-day события не занимают время, но в выдаче присутствовать должны."""
    gateway = FakeCalendarGateway()
    gateway.events = [all_day_event("vacation", date(2026, 7, 17))]

    result = await make_service_at(gateway).get_events(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    assert [event.event_id for event in result] == ["vacation"]


@pytest.mark.asyncio
async def test_get_events_includes_event_overlapping_range_boundary() -> None:
    """Событие, начавшееся вчера и идущее в запрошенный день, должно попасть в выдачу."""
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at(
            "overnight",
            datetime(2026, 7, 16, 23, 0, tzinfo=MOSCOW),
            duration_minutes=180,
        )
    ]

    result = await make_service_at(gateway).get_events(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    assert [event.event_id for event in result] == ["overnight"]


@pytest.mark.asyncio
async def test_get_events_rejects_inverted_range() -> None:
    with pytest.raises(CalendarInputError):
        await make_service_at(FakeCalendarGateway()).get_events(
            start_day_offset=5, end_day_offset=1, telegram_id=123
        )


@pytest.mark.asyncio
async def test_get_events_rejects_too_wide_range() -> None:
    """Диапазон приходит от LLM, поэтому ограничен на уровне сервиса."""
    with pytest.raises(CalendarInputError):
        await make_service_at(FakeCalendarGateway()).get_events(
            start_day_offset=0, end_day_offset=400, telegram_id=123
        )


@pytest.mark.asyncio
async def test_get_events_requires_telegram_id() -> None:
    with pytest.raises(CalendarAuthRequiredError):
        await make_service_at(FakeCalendarGateway()).get_events(
            start_day_offset=0, end_day_offset=1, telegram_id=None
        )


@pytest.mark.asyncio
async def test_free_slots_start_from_now_not_from_midnight() -> None:
    """Сейчас 10:00 — предлагать 03:00 или 09:30 нельзя."""
    gateway = FakeCalendarGateway()

    slots = await make_service_at(gateway).get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    assert slots
    first_start, _ = slots[0]
    assert first_start == datetime(2026, 7, 17, 10, 0, tzinfo=MOSCOW)


@pytest.mark.asyncio
async def test_free_slots_round_current_time_up_to_slot_boundary() -> None:
    """10:07 → первый слот начинается в 10:30, а не в 10:07."""
    gateway = FakeCalendarGateway()
    now_utc = datetime(2026, 7, 17, 7, 7, tzinfo=timezone.utc)  # 10:07 по Москве

    slots = await make_service_at(gateway, now_utc=now_utc).get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    first_start, _ = slots[0]
    assert first_start == datetime(2026, 7, 17, 10, 30, tzinfo=MOSCOW)


@pytest.mark.asyncio
async def test_free_slots_respect_working_hours() -> None:
    gateway = FakeCalendarGateway()

    slots = await make_service_at(gateway).get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    _, last_end = slots[-1]
    assert last_end == datetime(2026, 7, 17, 22, 0, tzinfo=MOSCOW)
    assert all(
        start.hour >= 8 and end.hour <= 22 or end == last_end for start, end in slots
    )


@pytest.mark.asyncio
async def test_free_slots_merge_into_continuous_intervals() -> None:
    """Свободное время отдаётся склеенными интервалами, а не по 30 минут."""
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at("meeting", datetime(2026, 7, 17, 14, 0, tzinfo=MOSCOW), duration_minutes=60)
    ]

    slots = await make_service_at(gateway).get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    assert slots == [
        (
            datetime(2026, 7, 17, 10, 0, tzinfo=MOSCOW),
            datetime(2026, 7, 17, 14, 0, tzinfo=MOSCOW),
        ),
        (
            datetime(2026, 7, 17, 15, 0, tzinfo=MOSCOW),
            datetime(2026, 7, 17, 22, 0, tzinfo=MOSCOW),
        ),
    ]


@pytest.mark.asyncio
async def test_free_slots_ignore_all_day_events() -> None:
    """Регрессия: раньше метка «на весь день» обнуляла свободное время."""
    gateway = FakeCalendarGateway()
    gateway.events = [all_day_event("birthday", date(2026, 7, 17))]

    slots = await make_service_at(gateway).get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    assert slots == [
        (
            datetime(2026, 7, 17, 10, 0, tzinfo=MOSCOW),
            datetime(2026, 7, 17, 22, 0, tzinfo=MOSCOW),
        )
    ]


@pytest.mark.asyncio
async def test_free_slots_filter_by_minimum_duration() -> None:
    """«Найди окно на два часа» — короткие промежутки не возвращаются."""
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at("a", datetime(2026, 7, 17, 11, 0, tzinfo=MOSCOW), duration_minutes=60),
        event_at("b", datetime(2026, 7, 17, 13, 0, tzinfo=MOSCOW), duration_minutes=60),
    ]

    service = make_service_at(gateway)
    all_slots = await service.get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )
    long_slots = await service.get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123, min_duration_minutes=120
    )

    assert (
        datetime(2026, 7, 17, 12, 0, tzinfo=MOSCOW),
        datetime(2026, 7, 17, 13, 0, tzinfo=MOSCOW),
    ) in all_slots
    assert all(end - start >= timedelta(minutes=120) for start, end in long_slots)
    assert len(long_slots) < len(all_slots)


@pytest.mark.asyncio
async def test_free_slots_return_empty_when_day_fully_booked() -> None:
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at(
            "marathon",
            datetime(2026, 7, 17, 8, 0, tzinfo=MOSCOW),
            duration_minutes=14 * 60,
        )
    ]

    slots = await make_service_at(gateway).get_free_slots(
        start_day_offset=0, end_day_offset=0, telegram_id=123
    )

    assert slots == []


@pytest.mark.asyncio
async def test_free_slots_rejects_invalid_minimum_duration() -> None:
    with pytest.raises(CalendarInputError):
        await make_service_at(FakeCalendarGateway()).get_free_slots(
            start_day_offset=0, end_day_offset=0, telegram_id=123, min_duration_minutes=0
        )


@pytest.mark.asyncio
async def test_free_slots_resolve_time_zone_once() -> None:
    """Регрессия: раньше get_free_slots ходил за таймзоной дважды."""
    gateway = FakeCalendarGateway()
    service = make_service_at(gateway)

    await service.get_free_slots(start_day_offset=0, end_day_offset=0, telegram_id=123)

    assert service._auth_service.get_user_time_zone.await_count == 1


@pytest.mark.asyncio
async def test_move_event_patches_instead_of_recreating() -> None:
    """Регрессия: перенос не должен удалять событие и терять название."""
    gateway = FakeCalendarGateway()

    result = await make_service_at(gateway).move_event(
        event_id="event-1",
        new_date="2026-07-18",
        new_time="16:00",
        duration_minutes=60,
        telegram_id=123,
    )

    assert gateway.deleted_event_id is None
    assert gateway.created is None
    assert gateway.updated == (
        "event-1",
        datetime(2026, 7, 18, 16, 0, tzinfo=MOSCOW),
        datetime(2026, 7, 18, 17, 0, tzinfo=MOSCOW),
    )
    assert result.event_id == "event-1"
    assert result.title == "Исходное название"


@pytest.mark.asyncio
async def test_move_event_rejects_busy_slot() -> None:
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at("occupied", datetime(2026, 7, 18, 16, 30, tzinfo=MOSCOW), duration_minutes=60)
    ]

    with pytest.raises(CalendarInputError):
        await make_service_at(gateway).move_event(
            event_id="event-1",
            new_date="2026-07-18",
            new_time="16:00",
            duration_minutes=60,
            telegram_id=123,
        )

    assert gateway.updated is None


@pytest.mark.asyncio
async def test_move_event_ignores_itself_when_checking_conflicts() -> None:
    """Сдвиг события на 30 минут не должен считаться конфликтом с самим собой."""
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at("event-1", datetime(2026, 7, 18, 16, 0, tzinfo=MOSCOW), duration_minutes=60)
    ]

    await make_service_at(gateway).move_event(
        event_id="event-1",
        new_date="2026-07-18",
        new_time="16:30",
        duration_minutes=60,
        telegram_id=123,
    )

    assert gateway.updated is not None


@pytest.mark.asyncio
async def test_move_event_ignores_all_day_events_as_conflicts() -> None:
    gateway = FakeCalendarGateway()
    gateway.events = [all_day_event("vacation", date(2026, 7, 18))]

    await make_service_at(gateway).move_event(
        event_id="event-1",
        new_date="2026-07-18",
        new_time="16:00",
        duration_minutes=60,
        telegram_id=123,
    )

    assert gateway.updated is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "new_date, new_time, duration_minutes",
    [
        ("18.07.2026", "16:00", 60),
        ("2026-07-18", "16:00:00", 60),
        ("2026-07-18", "16:00", 0),
        ("2026-07-18", "16:00", 1441),
        ("2026-07-18", "16:00", True),
    ],
)
async def test_move_event_rejects_invalid_arguments(
    new_date: str, new_time: str, duration_minutes: Any
) -> None:
    gateway = FakeCalendarGateway()

    with pytest.raises(CalendarInputError):
        await make_service_at(gateway).move_event(
            event_id="event-1",
            new_date=new_date,
            new_time=new_time,
            duration_minutes=duration_minutes,
            telegram_id=123,
        )

    assert gateway.updated is None


@pytest.mark.asyncio
@pytest.mark.parametrize("event_id", ["", "two ids", "x" * 1025])
async def test_move_event_rejects_invalid_event_id(event_id: str) -> None:
    with pytest.raises(CalendarInputError):
        await make_service_at(FakeCalendarGateway()).move_event(
            event_id=event_id,
            new_date="2026-07-18",
            new_time="16:00",
            duration_minutes=60,
            telegram_id=123,
        )


@pytest.mark.asyncio
async def test_upcoming_uses_user_zone_and_localizes_utc_events() -> None:
    gateway = FakeCalendarGateway()
    gateway.events = [event_at("meeting", datetime(2026, 7, 18, 15, tzinfo=timezone.utc))]

    events = await make_service_at(gateway).list_upcoming(123)

    assert gateway.request_time_zone == "Europe/Moscow"
    assert events[0].start.isoformat() == "2026-07-18T18:00:00+03:00"
    assert events[0].end.isoformat() == "2026-07-18T19:00:00+03:00"


@pytest.mark.asyncio
async def test_day_range_localizes_events_and_keeps_all_day_dates() -> None:
    gateway = FakeCalendarGateway()
    gateway.events = [
        event_at("meeting", datetime(2026, 7, 17, 15, tzinfo=timezone.utc)),
        all_day_event("holiday", date(2026, 7, 17)),
    ]

    events = await make_service_at(gateway).get_events(0, 0, 123)

    assert events[0].start.isoformat() == "2026-07-17T18:00:00+03:00"
    assert events[1].start == date(2026, 7, 17)


@pytest.mark.asyncio
async def test_create_18_moscow_sends_15_utc_and_localizes_google_response() -> None:
    created = event_at("meeting", datetime(2026, 7, 18, 15, tzinfo=timezone.utc))
    gateway = SimpleNamespace(create_event=AsyncMock(return_value=created))

    event = await make_service_at(gateway).create_from_text(
        "2026-07-18 18:00 30 Приготовить поесть", 123
    )

    arguments = gateway.create_event.await_args.kwargs
    assert arguments["time_zone"] == "Europe/Moscow"
    assert arguments["start"].isoformat() == "2026-07-18T18:00:00+03:00"
    assert arguments["start"].astimezone(timezone.utc).hour == 15
    assert event.start.hour == 18


@pytest.mark.asyncio
async def test_non_moscow_user_zone_is_respected() -> None:
    gateway = FakeCalendarGateway()

    await make_service_at(gateway, time_zone="Asia/Almaty").create_from_text(
        "2026-07-18 18:00 30 Встреча", 123
    )

    assert gateway.request_time_zone == "Asia/Almaty"
    assert gateway.created[1].astimezone(timezone.utc).hour == 13
