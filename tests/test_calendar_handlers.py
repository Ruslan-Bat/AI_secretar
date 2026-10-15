from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.calendar import (
    NOT_CONFIGURED_MESSAGE,
    create_router,
    handle_add_event,
    handle_calendar,
    handle_delete_event,
    handle_today,
    handle_timezone,
)
from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
    CalendarIntegrationError,
    CalendarTokenRefreshError,
)
from app.domain.calendar_event import CalendarEvent


@pytest.mark.asyncio
async def test_calendar_reports_missing_configuration() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await handle_calendar(message, None)

    message.answer.assert_awaited_once_with(NOT_CONFIGURED_MESSAGE)


@pytest.mark.asyncio
async def test_calendar_lists_events() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    event = CalendarEvent(
        event_id="event-id",
        title="Встреча",
        start=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
    )
    service = SimpleNamespace(list_upcoming=AsyncMock(return_value=[event]))

    await handle_calendar(message, service)

    response = message.answer.await_args.args[0]
    assert "Встреча" in response
    assert "event-id" in response


@pytest.mark.asyncio
async def test_today_reports_missing_configuration() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await handle_today(message, None)

    message.answer.assert_awaited_once_with(NOT_CONFIGURED_MESSAGE)


@pytest.mark.asyncio
async def test_today_lists_events_for_current_day() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    event = CalendarEvent(
        event_id="today-event-id",
        title="Сегодняшняя встреча",
        start=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
    )
    service = SimpleNamespace(get_events=AsyncMock(return_value=[event]))

    await handle_today(message, service)

    service.get_events.assert_awaited_once_with(
        start_day_offset=0,
        end_day_offset=0,
        telegram_id=123,
    )
    response = message.answer.await_args.args[0]
    assert "События на сегодня:" in response
    assert "Сегодняшняя встреча" in response
    assert "today-event-id" in response


@pytest.mark.asyncio
async def test_today_reports_empty_day() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    service = SimpleNamespace(get_events=AsyncMock(return_value=[]))

    await handle_today(message, service)

    message.answer.assert_awaited_once_with("На сегодня событий нет.")


@pytest.mark.asyncio
async def test_today_formats_all_day_event() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    event = CalendarEvent(
        event_id="all-day-id",
        title="Выходной",
        start=date(2026, 7, 20),
        end=date(2026, 7, 21),
    )
    service = SimpleNamespace(get_events=AsyncMock(return_value=[event]))

    await handle_today(message, service)

    response = message.answer.await_args.args[0]
    assert "20.07.2026 (весь день)" in response
    assert "Выходной" in response


@pytest.mark.asyncio
async def test_today_splits_long_event_list_into_telegram_sized_messages() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    events = [
        CalendarEvent(
            event_id=str(number) * 1024,
            title=f"Событие {number}",
            start=datetime(2026, 7, 20, 10 + number, tzinfo=timezone.utc),
            end=datetime(2026, 7, 20, 11 + number, tzinfo=timezone.utc),
        )
        for number in range(1, 5)
    ]
    service = SimpleNamespace(get_events=AsyncMock(return_value=events))

    await handle_today(message, service)

    responses = [call.args[0] for call in message.answer.await_args_list]
    assert len(responses) == 2
    assert all(len(response) <= 4000 for response in responses)
    assert all(
        any(f"Событие {number}" in response for response in responses)
        for number in range(1, 5)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (CalendarAuthRequiredError(), "Нужно пройти /login"),
        (CalendarTokenRefreshError(), "Не удалось обновить токен"),
        (
            CalendarIntegrationError(),
            "Не удалось обратиться к Google Calendar. Попробуйте позже.",
        ),
    ],
)
async def test_today_handles_calendar_errors(
    error: Exception,
    expected_message: str,
) -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    service = SimpleNamespace(get_events=AsyncMock(side_effect=error))

    await handle_today(message, service)

    message.answer.assert_awaited_once_with(expected_message)


@pytest.mark.asyncio
async def test_today_requires_telegram_user() -> None:
    message = SimpleNamespace(from_user=None, answer=AsyncMock())
    service = SimpleNamespace(get_events=AsyncMock())

    await handle_today(message, service)

    service.get_events.assert_not_awaited()
    message.answer.assert_awaited_once_with("Нужно пройти /login")


def test_today_command_is_registered() -> None:
    router = create_router()
    handler = next(
        item for item in router.message.handlers if item.callback is handle_today
    )

    assert handler.filters[0].callback.commands == ("today",)


@pytest.mark.asyncio
async def test_add_event_passes_command_arguments_to_service() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    command = SimpleNamespace(args="2026-07-20 14:30 60 Встреча")
    event = CalendarEvent(
        event_id="created-id",
        title="Встреча",
        start=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
    )
    service = SimpleNamespace(create_from_text=AsyncMock(return_value=event))

    await handle_add_event(message, command, service)

    service.create_from_text.assert_awaited_once_with(command.args, 123)
    assert "created-id" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_delete_event_passes_id_to_service() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    command = SimpleNamespace(args="event-id")
    service = SimpleNamespace(delete_from_text=AsyncMock())

    await handle_delete_event(message, command, service)

    service.delete_from_text.assert_awaited_once_with("event-id", 123)
    message.answer.assert_awaited_once_with("Событие удалено из Google Calendar.")


@pytest.mark.asyncio
async def test_timezone_shows_selected_zone() -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"), from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    service = SimpleNamespace(get_time_zone=AsyncMock(return_value="UTC"))

    await handle_timezone(message, SimpleNamespace(args=None), service)

    service.get_time_zone.assert_awaited_once_with(123)
    assert "Ваш часовой пояс: UTC" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_timezone_saves_user_choice() -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"), from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    service = SimpleNamespace(set_time_zone=AsyncMock(return_value="Europe/Moscow"))

    await handle_timezone(message, SimpleNamespace(args=" Europe/Moscow "), service)

    service.set_time_zone.assert_awaited_once_with(123, "Europe/Moscow")
    assert "Europe/Moscow" in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [CalendarInputError("Неверный пояс"), CalendarAuthRequiredError()])
async def test_timezone_reports_invalid_zone_or_missing_login(error: Exception) -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"), from_user=SimpleNamespace(id=123),
        answer=AsyncMock(),
    )
    service = SimpleNamespace(set_time_zone=AsyncMock(side_effect=error))

    await handle_timezone(message, SimpleNamespace(args="Europe/Moscow"), service)

    expected = "Нужно пройти /login" if isinstance(error, CalendarAuthRequiredError) else "Неверный пояс"
    message.answer.assert_awaited_once_with(expected)
