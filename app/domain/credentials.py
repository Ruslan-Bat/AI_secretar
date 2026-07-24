"""Доменная модель OAuth-токенов Google."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GoogleCredentials:
    """Учётные данные Google OAuth 2.0 для пользователя."""

    telegram_id: int
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    email: str | None = None