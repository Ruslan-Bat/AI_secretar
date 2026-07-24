"""Обрабатывает команду /login."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.google_auth import GoogleAuthService


async def handle_login(message: Message, auth_service: GoogleAuthService) -> None:
    """Генерирует ссылку для Google OAuth и отправляет её пользователю."""

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    # ВАЖНО: Защита от использования в группах
    if message.chat.type != "private":
        await message.answer("В целях безопасности авторизация доступна только в личных сообщениях с ботом.")
        return

    telegram_id = message.from_user.id
    
    # Генерируем ссылку
    auth_url = auth_service.build_authorization_url(telegram_id=telegram_id)

    await message.answer(
        "Чтобы бот мог работать с вашим календарем, авторизуйтесь по ссылке:\n\n"
        f"{auth_url}"
    )


def create_router() -> Router:
    router = Router(name="login")
    router.message.register(handle_login, Command("login"))
    return router