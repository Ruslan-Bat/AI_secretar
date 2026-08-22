from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from alembic.environment import Any
from pydantic import SecretStr
import pytest

from google.oauth2.credentials import Credentials

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


class FakeIntegrationWithMoscowExpiry(FakeIntegration):
    def refresh_credentials(self, credentials: SimpleNamespace) -> SimpleNamespace:
        self.refresh_called = True
        credentials.token = "refreshed-access-token"
        credentials.expiry = datetime.now(timezone(timedelta(hours=3))) + timedelta(hours=1)
        return credentials


def make_settings() -> Settings:
    return Settings(
        GOOGLE_CLIENT_ID="test-client-id",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        JWT_SECRET=SecretStr("test-secret-32-chars-1234567890"),
    )

class FakeCalendarGatewayForAuth:
    def __init__(self, time_zone: str | None = None, error: Exception | None = None) -> None:
        self._time_zone = time_zone
        self._error = error
        self.received_credentials: Any = None

    async def get_primary_calendar_timezone(self, user_credentials: Any = None) -> str:
        self.received_credentials = user_credentials
        if self._error is not None:
            raise self._error
        return self._time_zone


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
async def test_ensure_fresh_credentials_preserves_expiry_timezone_offset() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=4,
            access_token="expired-access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            email="user@example.com",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegrationWithMoscowExpiry()

    await service.ensure_fresh_credentials(4)

    assert repository.upserted is not None
    assert repository.upserted.expires_at is not None
    assert repository.upserted.expires_at.tzinfo == timezone.utc
    assert repository.upserted.expires_at == repository.upserted.expires_at.astimezone(timezone.utc)


class FakeIntegrationWithNaiveRefreshExpiry(FakeIntegration):
    def refresh_credentials(self, credentials: SimpleNamespace) -> SimpleNamespace:
        self.refresh_called = True
        credentials.token = "refreshed-access-token"
        credentials.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        # Simulate Google returning a naive expiry datetime
        credentials.expiry = credentials.expiry.replace(tzinfo=None)
        return credentials


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_normalizes_naive_refreshed_expiry() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=6,
            access_token="expired-access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            email="user@example.com",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegrationWithNaiveRefreshExpiry()

    credentials = await service.ensure_fresh_credentials(6)

    assert credentials.expiry is not None
    assert credentials.expiry.tzinfo is None
    assert repository.upserted is not None
    assert repository.upserted.expires_at is not None
    assert repository.upserted.expires_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_assumes_utc_for_naive_expiry() -> None:
    class FakeIntegrationWithNaiveExpiry(FakeIntegration):
        def exchange_code_for_tokens(self, code: str, state: str | None = None) -> dict[str, object]:
            tokens = super().exchange_code_for_tokens(code, state)
            tokens["expiry"] = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None).isoformat()
            return tokens

    repository = FakeCredentialsRepository(None)
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegrationWithNaiveExpiry()

    credentials = await service.exchange_code_for_tokens("code", telegram_id=1, state=None)

    assert credentials.expires_at is not None
    assert credentials.expires_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_raises_when_no_credentials() -> None:
    repository = FakeCredentialsRepository(None)
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegration()

    with pytest.raises(CalendarAuthRequiredError):
        await service.ensure_fresh_credentials(4)


@pytest.mark.asyncio
async def test_build_oauth_credentials_returns_google_credentials_object() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=5,
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            email="user@example.com",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    credentials = service.build_oauth_credentials(repository._credentials)

    assert isinstance(credentials, Credentials)
    assert credentials.token == "test-access-token"
    assert credentials.refresh_token == "test-refresh-token"
    assert credentials.client_id == "test-client-id"
    assert credentials.client_secret == "test-client-secret"
    assert credentials.token_uri == "https://oauth2.googleapis.com/token"
    assert credentials.scopes == service._integration._scopes
    assert credentials.expiry is not None
    assert credentials.expiry.tzinfo is None
    assert credentials.expiry == repository._credentials.expires_at.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_stores_timezone_from_gateway() -> None:
    repository = FakeCredentialsRepository(None)
    calendar_gateway = FakeCalendarGatewayForAuth(time_zone="Europe/Moscow")
    service = GoogleAuthService(
        settings=make_settings(),
        credentials_repo=repository,
        calendar_gateway=calendar_gateway,
    )
    service._integration = FakeIntegration()

    credentials = await service.exchange_code_for_tokens("code", telegram_id=7, state=None)

    assert credentials.time_zone == "Europe/Moscow"
    assert repository.upserted is not None
    assert repository.upserted.time_zone == "Europe/Moscow"
    assert calendar_gateway.received_credentials is not None
    assert calendar_gateway.received_credentials.token == "test-access-token"


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_keeps_timezone_none_when_gateway_missing() -> None:
    repository = FakeCredentialsRepository(None)
    service = GoogleAuthService(
        settings=make_settings(),
        credentials_repo=repository,
        calendar_gateway=None,
    )
    service._integration = FakeIntegration()

    credentials = await service.exchange_code_for_tokens("code", telegram_id=8, state=None)

    assert credentials.time_zone is None
    assert repository.upserted is not None
    assert repository.upserted.time_zone is None


@pytest.mark.asyncio
async def test_exchange_code_for_tokens_does_not_fail_login_when_timezone_fetch_errors() -> None:
    repository = FakeCredentialsRepository(None)
    calendar_gateway = FakeCalendarGatewayForAuth(error=RuntimeError("boom"))
    service = GoogleAuthService(
        settings=make_settings(),
        credentials_repo=repository,
        calendar_gateway=calendar_gateway,
    )
    service._integration = FakeIntegration()

    credentials = await service.exchange_code_for_tokens("code", telegram_id=9, state=None)

    assert credentials.time_zone is None
    assert repository.upserted is not None
    assert repository.upserted.time_zone is None


@pytest.mark.asyncio
async def test_ensure_fresh_credentials_preserves_timezone_on_refresh() -> None:
    repository = FakeCredentialsRepository(
        GoogleCredentials(
            telegram_id=10,
            access_token="expired-access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            email="user@example.com",
            time_zone="Asia/Almaty",
        )
    )
    service = GoogleAuthService(settings=make_settings(), credentials_repo=repository)
    service._integration = FakeIntegration()

    await service.ensure_fresh_credentials(10)

    assert repository.upserted is not None
    assert repository.upserted.time_zone == "Asia/Almaty"