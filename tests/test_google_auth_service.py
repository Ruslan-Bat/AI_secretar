from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import SecretStr
import pytest

from app.config import Settings
from app.core.calendar_exceptions import CalendarAuthRequiredError, CalendarTokenRefreshError
from app.domain.credentials import GoogleCredentials
from app.services.google_auth import GoogleAuthService


class FakeCredentialsRepository:
    def __init__(self, credentials: GoogleCredentials | None) -> None:
        self._credentials = credentials
        self.upserted: GoogleCredentials | None = None

    async def get_by_telegram_id(self, telegram_id: int) -> GoogleCredentials | None:
        return self._credentials

    async def upsert(self, credentials: GoogleCredentials) -> GoogleCredentials:
        self.upserted = credentials
        return credentials


class FakeIntegration:
    def __init__(self) -> None:
        self._scopes = ["https://www.googleapis.com/auth/calendar.events"]
        self.refresh_called = False

    def build_authorization_url(self, state: str | None = None) -> str:
        return "https://example.com/auth"

    def exchange_code_for_tokens(self, code: str, state: str | None = None) -> dict[str, object]:
        return {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "scopes": ["https://www.googleapis.com/auth/calendar.events"],
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "id_token": None,
            "state": state,
        }

    def build_credentials(self, tokens: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri"),
            expiry=tokens.get("expiry"),
        )

    def refresh_credentials(self, credentials: SimpleNamespace) -> SimpleNamespace:
        self.refresh_called = True
        credentials.token = "refreshed-access-token"
        credentials.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        return credentials


def make_settings() -> Settings:
    return Settings(
        GOOGLE_CLIENT_ID="test-client-id",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        JWT_SECRET=SecretStr("test-secret-32-chars-1234567890"),
    )


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_returns_current_token_when_not_expired() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=1,
            access_token="current-access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            email="user@example.com",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegration()

    credentials = await service.ensure_fresh_credentials(1)

    assert credentials.token == "current-access-token"
    assert not service._integration.refresh_called
    assert repository.upserted is None


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_refreshes_expired_token() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=2,
            access_token="expired-access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            email="user@example.com",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegration()

    credentials = await service.ensure_fresh_credentials(2)

    assert service._integration.refresh_called
    assert credentials.token == "refreshed-access-token"
    assert repository.upserted is not None
    assert repository.upserted.access_token == "refreshed-access-token"
    assert repository.upserted.expires_at is not None
    assert repository.upserted.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_raises_without_refresh_token() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=3,
            access_token="expired-access-token",
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            email="user@example.com",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegration()

    with pytest.raises(CalendarTokenRefreshError):
        await service.ensure_fresh_credentials(3)

    assert not service._integration.refresh_called


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_raises_when_no_credentials() -> None:
    repository = FakeCredentialsRepository(None)
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegration()

    with pytest.raises(CalendarAuthRequiredError):
        await service.ensure_fresh_credentials(4)
