import asyncio
from typing import Any

import pytest

from app.bot import lifecycle
from app.config import Settings
from app.dependencies import build_container
from tests.constants import DUMMY_BOT_TOKEN


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBot:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.delete_webhook_called = False
        self.webhook: tuple[str, str | None] | None = None

    async def delete_webhook(self, *, drop_pending_updates: bool) -> None:
        assert drop_pending_updates is False
        self.delete_webhook_called = True

    async def set_webhook(self, url: str, *, secret_token: str | None) -> None:
        self.webhook = (url, secret_token)


class FakeDispatcher:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stop_requested = asyncio.Event()
        self.stopped = asyncio.Event()
        self.stop_polling_called = False
        self.outer_task_cancelled = False

    async def start_polling(self, bot: Any, **kwargs: Any) -> None:
        assert kwargs["handle_signals"] is False
        assert kwargs["close_bot_session"] is False
        self.started.set()
        try:
            await self.stop_requested.wait()
        except asyncio.CancelledError:
            self.outer_task_cancelled = True
            raise
        finally:
            self.stopped.set()

    async def stop_polling(self) -> None:
        self.stop_polling_called = True
        self.stop_requested.set()
        await self.stopped.wait()


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "BOT_TOKEN": DUMMY_BOT_TOKEN,
        "DEBUG": False,
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "BOT_MODE": "polling",
        "WEBHOOK_BASE_URL": None,
        "WEBHOOK_PATH": "/telegram/webhook",
        "WEBHOOK_SECRET": None,
        "GOOGLE_CALENDAR_ENABLED": False,
        "TESTING": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_polling_runtime_starts_and_stops_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = FakeBot()
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(lifecycle, "create_bot", lambda settings: bot)
    monkeypatch.setattr(
        lifecycle,
        "create_dispatcher",
        lambda user_service, calendar_service, auth_service: dispatcher,
    )

    runtime = await lifecycle.start_bot_runtime(make_settings(), build_container())
    await asyncio.wait_for(dispatcher.started.wait(), timeout=1)

    assert bot.delete_webhook_called is True
    assert runtime.polling_task is not None

    await lifecycle.stop_bot_runtime(runtime)

    assert dispatcher.stop_polling_called is True
    assert dispatcher.outer_task_cancelled is False
    assert runtime.polling_task.done()
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_webhook_runtime_builds_url_and_sets_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeBot()
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(lifecycle, "create_bot", lambda settings: bot)
    monkeypatch.setattr(
        lifecycle,
        "create_dispatcher",
        lambda user_service, calendar_service, auth_service: dispatcher,
    )
    settings = make_settings(
        BOT_MODE="webhook",
        WEBHOOK_BASE_URL="https://example.test/",
        WEBHOOK_PATH="telegram/webhook",
        WEBHOOK_SECRET="test-webhook-secret",
    )

    runtime = await lifecycle.start_bot_runtime(settings, build_container())

    assert runtime.polling_task is None
    assert bot.webhook == (
        "https://example.test/telegram/webhook",
        "test-webhook-secret",
    )

    await lifecycle.stop_bot_runtime(runtime)
    assert bot.session.closed is True
