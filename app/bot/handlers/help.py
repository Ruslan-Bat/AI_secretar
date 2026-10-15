"""Обрабатывает команду /help."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


async def handle_help(message: Message) -> None:
    await message.answer(
        "Подключение календаря:\n"
        "/start — начать работу\n"
        "/login — подключить свой Google Calendar\n\n"
        "Просмотр событий:\n"
        "/today — все события на сегодня\n"
        "/calendar — ближайшие события\n\n"
        "Создать событие:\n"
        "/add_event ГГГГ-ММ-ДД ЧЧ:ММ МИНУТЫ НАЗВАНИЕ\n"
        "МИНУТЫ — длительность; время указывайте через двоеточие.\n\n"
        "Удалить событие:\n"
        "/delete_event EVENT_ID\n"
        "ID можно скопировать из ответа /today или /calendar.\n\n"
        "Часовой пояс:\n"
        "/timezone — показать текущий пояс\n"
        "/timezone Europe/Moscow — установить московское время\n"
        "Время в командах и ответах используется в выбранном поясе.\n\n"
        "/help — справка\n"
        "/ping — проверить работу бота",
        parse_mode=None,
    )


def create_router() -> Router:
    router = Router(name="help")
    router.message.register(handle_help, Command("help"))
    return router
