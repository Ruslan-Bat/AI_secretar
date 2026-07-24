from datetime import datetime, timezone

import pytest

from app.repositories.memory_user import MemoryUserRepository
from app.services.user import UserService


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


@pytest.mark.asyncio
async def test_registers_new_user() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repository = MemoryUserRepository()
    service = UserService(repository, clock=SequenceClock(timestamp))

    user = await service.register_or_update(
        telegram_id=101,
        username="new_user",
        first_name="New",
        last_name="User",
        language_code="ru",
    )

    assert user.telegram_id == 101
    assert user.username == "new_user"
    assert user.created_at == timestamp
    assert user.updated_at == timestamp
    assert await repository.count() == 1


@pytest.mark.asyncio
async def test_updates_existing_user_and_preserves_created_at() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    repository = MemoryUserRepository()
    service = UserService(
        repository,
        clock=SequenceClock(created_at, updated_at),
    )

    original = await service.register_or_update(
        telegram_id=101,
        username="old_name",
        first_name="Old",
    )
    updated = await service.register_or_update(
        telegram_id=101,
        username="new_name",
        first_name="New",
        language_code="en",
    )

    assert updated.username == "new_name"
    assert updated.first_name == "New"
    assert updated.language_code == "en"
    assert updated.created_at == original.created_at == created_at
    assert updated.updated_at == updated_at
    assert updated.updated_at > original.updated_at
    assert await repository.count() == 1
