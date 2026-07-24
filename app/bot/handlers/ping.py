"""Обрабатывает команду /ping."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


async def handle_ping(message: Message) -> None:
    await message.answer("Ядро работает.")


def create_router() -> Router:
    router = Router(name="ping")
    router.message.register(handle_ping, Command("ping"))
    return router
