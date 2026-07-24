"""Создаёт новый набор маршрутов aiogram для каждого экземпляра приложения."""

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from app.bot.handlers import (
    create_calendar_router,
    create_help_router,
    create_login_router,
    create_ping_router,
    create_start_router,
)


logger = logging.getLogger(__name__)


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    logger.error(
        "Unhandled Telegram handler error (%s)",
        type(event.exception).__name__,
    )

    message = event.update.message
    if message is not None:
        try:
            await message.answer("Произошла ошибка. Попробуйте ещё раз позже.")
        except Exception as response_error:
            logger.warning(
                "Could not send neutral error response (%s)",
                type(response_error).__name__,
            )
    return True


def create_root_router() -> Router:
    router = Router(name="root")
    router.include_router(create_start_router())
    router.include_router(create_help_router())
    router.include_router(create_ping_router())
    router.include_router(create_calendar_router())
    router.include_router(create_login_router())
    router.errors.register(handle_unexpected_error)
    return router
