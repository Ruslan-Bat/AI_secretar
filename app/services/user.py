"""Бизнес-операции с пользователями Telegram."""

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.domain.user import User
from app.repositories.user import UserRepository


logger = logging.getLogger(__name__)
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserService:
    def __init__(self, repository: UserRepository, *, clock: Clock = utc_now) -> None:
        self._repository = repository
        self._clock = clock

    async def register_or_update(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> User:
        existing = await self._repository.get_by_telegram_id(telegram_id)
        now = self._clock()

        if existing is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                created_at=now,
                updated_at=now,
            )
            logger.info("Registered Telegram user id=%s", telegram_id)
        else:
            if now <= existing.updated_at:
                now = existing.updated_at + timedelta(microseconds=1)
            user = replace(
                existing,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                updated_at=now,
            )
            logger.info("Updated Telegram user id=%s", telegram_id)

        return await self._repository.upsert(user)

    async def register_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> User:
        """Совместимый псевдоним операции регистрации или обновления."""

        return await self.register_or_update(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
