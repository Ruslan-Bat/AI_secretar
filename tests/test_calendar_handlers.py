from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.calendar import (
    NOT_CONFIGURED_MESSAGE,
    handle_add_event,
    handle_calendar,
    handle_delete_event,
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
async def test_add_event_passes_command_arguments_to_service() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    command = SimpleNamespace(args="2026-07-20 14:30 60 Встреча")
    event = CalendarEvent(
        event_id="created-id",
        title="Встреча",
        start=datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
    )
    service = SimpleNamespace(create_from_text=AsyncMock(return_value=event))

    await handle_add_event(message, command, service)

    service.create_from_text.assert_awaited_once_with(command.args)
    assert "created-id" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_delete_event_passes_id_to_service() -> None:
    message = SimpleNamespace(answer=AsyncMock())
    command = SimpleNamespace(args="event-id")
    service = SimpleNamespace(delete_from_text=AsyncMock())

    await handle_delete_event(message, command, service)

    service.delete_from_text.assert_awaited_once_with("event-id")
    message.answer.assert_awaited_once_with("Событие удалено из Google Calendar.")
