from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from app.api.google_auth import router
from app.dependencies import get_google_auth_service


def make_app(username: str = "Secretartest_bot"):
    application = FastAPI()
    application.include_router(router)
    auth = SimpleNamespace(
        verify_state_token=Mock(return_value=123),
        exchange_code_for_tokens=AsyncMock(),
    )
    bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(username=username)))
    application.state.bot_runtime = SimpleNamespace(bot=bot)
    application.dependency_overrides[get_google_auth_service] = lambda: auth
    return application, auth, bot


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["Secretartest_bot", "another_calendar_bot"])
async def test_callback_redirects_to_bot_from_active_token(username: str) -> None:
    application, auth, bot = make_app(username)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.get("/auth/google/callback?code=test-code&state=test-state")

    assert response.status_code == 307
    assert response.headers["location"] == f"https://t.me/{username}?start=auth_success"
    auth.exchange_code_for_tokens.assert_awaited_once_with(
        code="test-code", telegram_id=123, state="test-state"
    )
    bot.me.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_state_does_not_exchange_tokens() -> None:
    application, auth, bot = make_app()
    auth.verify_state_token.side_effect = ValueError("Ссылка устарела")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.get("/auth/google/callback?code=test-code&state=bad-state")

    assert response.status_code == 400
    auth.exchange_code_for_tokens.assert_not_awaited()
    bot.me.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_bot_runtime_does_not_exchange_tokens() -> None:
    application, auth, _ = make_app()
    application.state.bot_runtime = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.get("/auth/google/callback?code=test-code&state=test-state")

    assert response.status_code == 500
    auth.exchange_code_for_tokens.assert_not_awaited()
