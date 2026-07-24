import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app
from tests.constants import DUMMY_BOT_TOKEN


def make_test_settings() -> Settings:
    return Settings(
        _env_file=None,
        BOT_TOKEN=DUMMY_BOT_TOKEN,
        DEBUG=False,
        HOST="127.0.0.1",
        PORT=8000,
        BOT_MODE="polling",
        WEBHOOK_BASE_URL=None,
        WEBHOOK_PATH="/telegram/webhook",
        WEBHOOK_SECRET=None,
        GOOGLE_CALENDAR_ENABLED=False,
        TESTING=True,
    )


@pytest.mark.asyncio
async def test_health_returns_expected_contract() -> None:
    application = create_app(make_test_settings())

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "telegram-calendar-bot",
        "bot_mode": "polling",
    }
    assert DUMMY_BOT_TOKEN not in response.text


@pytest.mark.asyncio
async def test_application_starts_in_testing_mode_without_telegram() -> None:
    application = create_app(make_test_settings())

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert application.state.bot_runtime is None


def test_create_app_can_be_called_more_than_once() -> None:
    first = create_app(make_test_settings())
    second = create_app(make_test_settings())

    assert isinstance(first, FastAPI)
    assert isinstance(second, FastAPI)
    assert first.state.container is not second.state.container
    assert first.state.container.user_repository is not second.state.container.user_repository


@pytest.mark.asyncio
async def test_google_auth_callback_route_is_registered() -> None:
    application = create_app(make_test_settings())

    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/auth/google/callback?code=test-code&state=123",
                follow_redirects=False,
            )

    assert response.status_code in {400, 500}
    assert response.headers.get("content-type", "").startswith("application/json") or response.headers.get("content-type", "").startswith("text/plain")
