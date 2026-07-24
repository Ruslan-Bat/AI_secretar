from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.help import handle_help
from app.bot.handlers.ping import handle_ping
from app.bot.handlers.start import handle_start


@pytest.mark.asyncio
async def test_start_registers_user_and_replies() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(
            id=101,
            username="tester",
            first_name="Test",
            last_name="User",
            language_code="ru",
        ),
        answer=AsyncMock(),
    )
    user_service = SimpleNamespace(register_or_update=AsyncMock())

    await handle_start(message, user_service)

    user_service.register_or_update.assert_awaited_once_with(
        telegram_id=101,
        username="tester",
        first_name="Test",
        last_name="User",
        language_code="ru",
    )
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_help_lists_all_commands() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await handle_help(message)

    response = message.answer.await_args.args[0]
    assert "/start" in response
    assert "/help" in response
    assert "/ping" in response
    assert "/calendar" in response
    assert "/add_event" in response
    assert "/delete_event" in response


@pytest.mark.asyncio
async def test_ping_replies_that_core_is_running() -> None:
    message = SimpleNamespace(answer=AsyncMock())

    await handle_ping(message)

    message.answer.assert_awaited_once_with("Ядро работает.")
