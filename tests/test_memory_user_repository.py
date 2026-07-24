from datetime import datetime, timezone

import pytest

from app.domain.user import User
from app.repositories.memory_user import MemoryUserRepository


def make_user(telegram_id: int, *, username: str = "initial") -> User:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return User(
        telegram_id=telegram_id,
        username=username,
        first_name="Test",
        last_name="User",
        language_code="ru",
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_upsert_saves_and_gets_user() -> None:
    repository = MemoryUserRepository()
    user = make_user(101)

    stored = await repository.upsert(user)

    assert stored == user
    assert await repository.get_by_telegram_id(101) == user
    assert await repository.get_by_telegram_id(999) is None


@pytest.mark.asyncio
async def test_upsert_updates_existing_user_without_growing_count() -> None:
    repository = MemoryUserRepository()
    await repository.upsert(make_user(101))

    updated = make_user(101, username="updated")
    await repository.upsert(updated)

    assert await repository.get_by_telegram_id(101) == updated
    assert await repository.count() == 1


@pytest.mark.asyncio
async def test_count_tracks_unique_users() -> None:
    repository = MemoryUserRepository()
    assert await repository.count() == 0

    await repository.upsert(make_user(101))
    await repository.upsert(make_user(202))

    assert await repository.count() == 2


@pytest.mark.asyncio
async def test_repository_instances_do_not_share_state() -> None:
    first = MemoryUserRepository()
    second = MemoryUserRepository()
    await first.upsert(make_user(101))

    assert await first.count() == 1
    assert await second.count() == 0
    assert await second.get_by_telegram_id(101) is None
