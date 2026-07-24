"""Запускает опрос или вебхук и штатно завершает внутренние задачи aiogram."""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from aiogram import Bot, Dispatcher

from app.bot.dispatcher import create_dispatcher
from app.bot.factory import create_bot
from app.config import Settings
from app.dependencies import AppContainer


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotRuntime:
    bot: Bot
    dispatcher: Dispatcher
    polling_task: asyncio.Task[None] | None = None


def _log_polling_result(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    if error is not None:
        logger.error("Polling stopped unexpectedly (%s)", type(error).__name__)


async def start_bot_runtime(
    settings: Settings,
    container: AppContainer,
) -> BotRuntime:
    settings.validate_runtime()
    bot = create_bot(settings)
    dispatcher = create_dispatcher(
        container.user_service,
        container.calendar_service,
        container.auth_service,
    )
    runtime = BotRuntime(bot=bot, dispatcher=dispatcher)

    try:
        if settings.BOT_MODE == "polling":
            logger.info("Starting Telegram polling")
            await bot.delete_webhook(drop_pending_updates=False)
            runtime.polling_task = asyncio.create_task(
                dispatcher.start_polling(
                    bot,
                    handle_signals=False,
                    close_bot_session=False,
                ),
                name="telegram-polling",
            )
            runtime.polling_task.add_done_callback(_log_polling_result)
        else:
            webhook_url = f"{settings.WEBHOOK_BASE_URL}{settings.WEBHOOK_PATH}"
            logger.info("Configuring Telegram webhook")
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.webhook_secret(),
            )
    except Exception as error:
        await bot.session.close()
        logger.error("Telegram startup failed (%s)", type(error).__name__)
        raise RuntimeError(
            "Telegram startup failed; check bot configuration and network access"
        ) from None

    return runtime


async def stop_bot_runtime(runtime: BotRuntime) -> None:
    task = runtime.polling_task
    if task is not None:
        logger.info("Stopping Telegram polling")
        if not task.done():
            try:
                # Даём aiogram отменить и дождаться своих задач опроса.
                await runtime.dispatcher.stop_polling()
            except RuntimeError:
                # При очень ранней остановке фоновая задача может не успеть
                # получить внутреннюю блокировку запуска aiogram.
                task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as error:
            logger.error("Polling shutdown error (%s)", type(error).__name__)

    with suppress(Exception):
        await runtime.bot.session.close()
    logger.info("Telegram runtime stopped")
