"""Тесты для SqlCredentialsRepository.

on_conflict_do_update — PostgreSQL-специфичная конструкция, поэтому эти
тесты требуют реального подключения к Postgres и не могут быть
проверены на SQLite или через моки сессии. Подключение задаётся через
переменную окружения TEST_DATABASE_URL; при её отсутствии тесты
пропускаются, а не падают.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.credentials import GoogleCredentials
from app.repositories.sql_user import SqlCredentialsRepository, metadata, users_table

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
#TODO: создать docker - compose с тестовым posgres для CI

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "TEST_DATABASE_URL is not set; SqlCredentialsRepository requires a real "
        "PostgreSQL instance because it relies on the PostgreSQL-specific "
        "ON CONFLICT DO UPDATE construct, which cannot run against SQLite or a mock."
    ),
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async with engine.begin() as connection:
        await connection.run_sync(metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _seed_parent_users(session_factory: async_sessionmaker) -> None:
    """google_credentials.telegram_id — внешний ключ на users.telegram_id,
    поэтому перед вставкой credentials нужны родительские записи пользователей."""
    async with session_factory() as session:
        await session.execute(
            pg_insert(users_table).values(
                [{"telegram_id": telegram_id} for telegram_id in range(1, 21)]
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def repository(session_factory: async_sessionmaker) -> SqlCredentialsRepository:
    return SqlCredentialsRepository(session_factory=session_factory)


@pytest.mark.asyncio
async def test_get_by_telegram_id_returns_none_when_missing(
    repository: SqlCredentialsRepository,
) -> None:
    result = await repository.get_by_telegram_id(999)
    assert result is None


@pytest.mark.asyncio
async def test_upsert_inserts_new_credentials_with_all_fields(
    repository: SqlCredentialsRepository,
) -> None:
    credentials = GoogleCredentials(
        telegram_id=1,
        access_token="access-token-1",
        refresh_token="refresh-token-1",
        expires_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        email="user1@example.com",
        time_zone="Europe/Moscow",
    )

    result = await repository.upsert(credentials)

    assert result.telegram_id == 1
    assert result.access_token == "access-token-1"
    assert result.refresh_token == "refresh-token-1"
    assert result.email == "user1@example.com"
    assert result.time_zone == "Europe/Moscow"
    assert result.expires_at == datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    fetched = await repository.get_by_telegram_id(1)
    assert fetched == result


@pytest.mark.asyncio
async def test_upsert_inserts_new_credentials_with_null_timezone(
    repository: SqlCredentialsRepository,
) -> None:
    credentials = GoogleCredentials(telegram_id=2, access_token="access-token-2", time_zone=None)

    result = await repository.upsert(credentials)

    assert result.time_zone is None
    fetched = await repository.get_by_telegram_id(2)
    assert fetched is not None
    assert fetched.time_zone is None


@pytest.mark.asyncio
async def test_upsert_updates_timezone_when_new_value_provided(
    repository: SqlCredentialsRepository,
) -> None:
    await repository.upsert(
        GoogleCredentials(telegram_id=3, access_token="token-a", time_zone="Europe/Moscow")
    )

    updated = await repository.upsert(
        GoogleCredentials(telegram_id=3, access_token="token-b", time_zone="Asia/Almaty")
    )

    assert updated.time_zone == "Asia/Almaty"
    assert updated.access_token == "token-b"


@pytest.mark.asyncio
async def test_upsert_preserves_existing_timezone_when_not_provided(
    repository: SqlCredentialsRepository,
) -> None:
    """Регрессионный тест: обновление токена (например, при refresh в
    ensure_fresh_credentials) не должно затирать ранее сохранённую
    таймзону значением None."""
    await repository.upsert(
        GoogleCredentials(telegram_id=4, access_token="token-a", time_zone="Europe/Moscow")
    )

    updated = await repository.upsert(
        GoogleCredentials(telegram_id=4, access_token="token-b", time_zone=None)
    )

    assert updated.time_zone == "Europe/Moscow"
    assert updated.access_token == "token-b"

    fetched = await repository.get_by_telegram_id(4)
    assert fetched is not None
    assert fetched.time_zone == "Europe/Moscow"


@pytest.mark.asyncio
async def test_upsert_preserves_existing_email_when_not_provided(
    repository: SqlCredentialsRepository,
) -> None:
    await repository.upsert(
        GoogleCredentials(telegram_id=5, access_token="token-a", email="user5@example.com")
    )

    updated = await repository.upsert(
        GoogleCredentials(telegram_id=5, access_token="token-b", email=None)
    )

    assert updated.email == "user5@example.com"


@pytest.mark.asyncio
async def test_upsert_preserves_existing_refresh_token_when_not_provided(
    repository: SqlCredentialsRepository,
) -> None:
    await repository.upsert(
        GoogleCredentials(telegram_id=6, access_token="token-a", refresh_token="refresh-a")
    )

    updated = await repository.upsert(
        GoogleCredentials(telegram_id=6, access_token="token-b", refresh_token=None)
    )

    assert updated.refresh_token == "refresh-a"
    assert updated.access_token == "token-b"


@pytest.mark.asyncio
async def test_upsert_always_overwrites_access_token_and_expires_at(
    repository: SqlCredentialsRepository,
) -> None:
    await repository.upsert(
        GoogleCredentials(
            telegram_id=7,
            access_token="token-a",
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )

    updated = await repository.upsert(
        GoogleCredentials(
            telegram_id=7,
            access_token="token-b",
            expires_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
    )

    assert updated.access_token == "token-b"
    assert updated.expires_at == datetime(2026, 2, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_delete_by_telegram_id_removes_existing_credentials(
    repository: SqlCredentialsRepository,
) -> None:
    await repository.upsert(GoogleCredentials(telegram_id=8, access_token="token-a"))

    deleted = await repository.delete_by_telegram_id(8)

    assert deleted is True
    assert await repository.get_by_telegram_id(8) is None


@pytest.mark.asyncio
async def test_delete_by_telegram_id_returns_false_when_nothing_to_delete(
    repository: SqlCredentialsRepository,
) -> None:
    deleted = await repository.delete_by_telegram_id(9999)
    assert deleted is False