"""Интерфейс хранилища пользователей, не зависящий от способа хранения."""

from typing import Protocol, runtime_checkable

from app.domain.user import User


@runtime_checkable
class UserRepository(Protocol):
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Возвращает пользователя по идентификатору Telegram, если он существует."""
        ...

    async def upsert(self, user: User) -> User:
        """Добавляет или обновляет пользователя и возвращает сохранённое значение."""
        ...

    async def count(self) -> int:
        """Возвращает количество сохранённых пользователей."""
        ...