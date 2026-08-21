"""PostgreSQL-репозиторий пользователей Telegram и их Google Credentials."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, func, select, ForeignKey
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping, CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.domain.credentials import GoogleCredentials
from app.domain.user import User


metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("telegram_id", BigInteger, primary_key=True),
    Column("username", String(255), nullable=True),
    Column("first_name", String(255), nullable=True),
    Column("last_name", String(255), nullable=True),
    Column("language_code", String(32), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)

google_credentials_table = Table(
    "google_credentials",
    metadata,
    Column(
        "telegram_id",
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("email", String(255), nullable=True),
    Column("access_token", String, nullable=False),
    Column("refresh_token", String, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("time_zone", String(64), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)

def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _row_to_user(row: RowMapping) -> User:
    return User(
        telegram_id=int(row["telegram_id"]),
        username=row["username"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        language_code=row["language_code"],
        created_at=_ensure_aware_utc(row["created_at"]),
        updated_at=_ensure_aware_utc(row["updated_at"]),
    )

def _row_to_credentials(row: RowMapping) -> GoogleCredentials:
    return GoogleCredentials(
        telegram_id=int(row["telegram_id"]),
        email=row["email"],
        access_token=row["access_token"],
        refresh_token=row["refresh_token"],
        expires_at=_ensure_aware_utc(row["expires_at"]) if row["expires_at"] else None,
        time_zone=row["time_zone"],
    )


class SqlUserRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(users_table).where(users_table.c.telegram_id == telegram_id)
            )
            row = result.mappings().first()
            return None if row is None else _row_to_user(row)

    async def upsert(self, user: User) -> User:
        async with self._session_factory() as session:
            statement = (
                pg_insert(users_table)
                .values(
                    telegram_id=user.telegram_id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
                .on_conflict_do_update(
                    index_elements=[users_table.c.telegram_id],
                    set_={
                        "username": user.username,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "language_code": user.language_code,
                        "updated_at": user.updated_at,
                    },
                )
                .returning(users_table)
            )
            result = await session.execute(statement)
            await session.commit()
            row = result.mappings().one()
            return _row_to_user(row)

    async def count(self) -> int:
        async with self._session_factory() as session:
            result = await session.execute(select(func.count()).select_from(users_table))
            return int(result.scalar_one())


class SqlCredentialsRepository:
    """Репозиторий для управления Google Credentials пользователей."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        if session_factory:
            self._session_factory = session_factory
        else:
            raise ValueError("Either database_url or session_factory must be provided")

    async def get_by_telegram_id(self, telegram_id: int) -> GoogleCredentials | None:
        """Получить токены Google по telegram_id."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(google_credentials_table).where(
                    google_credentials_table.c.telegram_id == telegram_id
                )
            )
            row = result.mappings().first()
            return None if row is None else _row_to_credentials(row)

    async def upsert(self, credentials: GoogleCredentials) -> GoogleCredentials:
        """Сохранить или обновить токены Google для пользователя."""
        async with self._session_factory() as session:
            update_values = {
                "access_token": credentials.access_token,
                "expires_at": credentials.expires_at,
                "updated_at": func.now(),
            }
            if credentials.email is not None:
                update_values["email"] = credentials.email
            if credentials.refresh_token is not None:
                update_values["refresh_token"] = credentials.refresh_token
            if credentials.time_zone is not None:
                update_values["time_zone"] = credentials.time_zone

            statement = (
                pg_insert(google_credentials_table)
                .values(
                    telegram_id=credentials.telegram_id,
                    email=credentials.email,
                    access_token=credentials.access_token,
                    refresh_token=credentials.refresh_token,
                    expires_at=credentials.expires_at,
                    time_zone=credentials.time_zone,
                )
                .on_conflict_do_update(
                    index_elements=[google_credentials_table.c.telegram_id],
                    set_=update_values,
                )
                .returning(google_credentials_table)
            )
            result = await session.execute(statement)
            await session.commit()
            row = result.mappings().one()
            return _row_to_credentials(row)

    async def delete_by_telegram_id(self, telegram_id: int) -> bool:
        """Удалить токены пользователя (например, при отвязке аккаунта)."""
        async with self._session_factory() as session:
            statement = google_credentials_table.delete().where(
                google_credentials_table.c.telegram_id == telegram_id
            )
            result = await session.execute(statement)
            await session.commit()
            if isinstance(result, CursorResult):
                return result.rowcount > 0
            return False