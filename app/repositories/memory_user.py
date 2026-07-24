"""Хранит пользователей в памяти для локальной версии приложения."""

from app.domain.user import User


class MemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return self._users.get(telegram_id)

    async def upsert(self, user: User) -> User:
        self._users[user.telegram_id] = user
        return user

    async def count(self) -> int:
        return len(self._users)
