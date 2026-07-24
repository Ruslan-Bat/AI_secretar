"""Обрабатывает команду /help."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


async def handle_help(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/start — запустить и зарегистрировать пользователя\n"
        "/help — показать эту справку\n"
        "/ping — проверить работу ядра\n"
        "/calendar — ближайшие события Google Calendar\n"
        "/add_event ГГГГ-ММ-ДД ЧЧ:ММ МИНУТЫ НАЗВАНИЕ\n"
        "/delete_event EVENT_ID — удалить событие"
    )


def create_router() -> Router:
    router = Router(name="help")
    router.message.register(handle_help, Command("help"))
    return router
