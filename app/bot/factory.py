"""Создаёт экземпляр Telegram-бота."""

from aiogram import Bot

from app.config import Settings


def create_bot(settings: Settings) -> Bot:
    return Bot(token=settings.telegram_token())
