"""Создаёт и настраивает диспетчер aiogram."""

from aiogram import Dispatcher

from app.bot.routers import create_root_router
from app.services.calendar import CalendarService
from app.services.user import UserService
from app.services.google_auth import GoogleAuthService  # Добавлен импорт


def create_dispatcher(
    user_service: UserService,
    calendar_service: CalendarService | None = None,
    auth_service: GoogleAuthService | None = None,  # Добавлен параметр
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher["user_service"] = user_service
    dispatcher["calendar_service"] = calendar_service
    dispatcher["auth_service"] = auth_service  # Регистрация зависимости
    dispatcher.include_router(create_root_router())
    return dispatcher