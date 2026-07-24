"""Принимает обновления Telegram в режиме вебхука."""

import secrets
from typing import Annotated, Any

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.bot.lifecycle import BotRuntime
from app.config import Settings


def create_webhook_router(path: str) -> APIRouter:
    router = APIRouter()

    @router.post(path, status_code=status.HTTP_200_OK)
    async def telegram_webhook(
        payload: dict[str, Any],
        request: Request,
        telegram_secret: Annotated[
            str | None,
            Header(alias="X-Telegram-Bot-Api-Secret-Token"),
        ] = None,
    ) -> dict[str, bool]:
        settings: Settings = request.app.state.settings
        expected_secret = settings.webhook_secret()
        if expected_secret and (
            telegram_secret is None
            or not secrets.compare_digest(telegram_secret, expected_secret)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook secret",
            )

        runtime: BotRuntime | None = request.app.state.bot_runtime
        if settings.BOT_MODE != "webhook" or runtime is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook mode is not active",
            )

        try:
            update = Update.model_validate(
                payload,
                context={"bot": runtime.bot},
            )
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Telegram update",
            ) from None

        await runtime.dispatcher.feed_update(runtime.bot, update)
        return {"ok": True}

    return router
