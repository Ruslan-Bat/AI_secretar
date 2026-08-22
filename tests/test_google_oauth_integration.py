"""Тесты для GoogleOAuthIntegration."""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials
from pydantic import SecretStr

from app.config import Settings
from app.integrations.google_auth import GoogleOAuthIntegration


def make_settings() -> Settings:
    return Settings(
        GOOGLE_CLIENT_ID="test-client-id",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        JWT_SECRET=SecretStr("test-secret-32-chars-1234567890"),
    )


def test_scopes_include_required_permissions() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())

    assert "https://www.googleapis.com/auth/calendar.events" in integration._scopes
    assert "https://www.googleapis.com/auth/calendar.calendars.readonly" in integration._scopes
    assert "https://www.googleapis.com/auth/userinfo.email" in integration._scopes
    assert "https://www.googleapis.com/auth/userinfo.profile" in integration._scopes


def test_build_authorization_url_returns_google_auth_url() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())

    url = integration.build_authorization_url(state=None)
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/auth"
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["http://localhost:8000/auth/google/callback"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["include_granted_scopes"] == ["true"]


def test_build_authorization_url_requests_calendar_readonly_scope() -> None:
    """Сквозная проверка: новый scope не просто объявлен в _scopes,
    а реально попадает в сгенерированный запрос авторизации."""
    integration = GoogleOAuthIntegration(settings=make_settings())

    url = integration.build_authorization_url(state=None)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    requested_scopes = query["scope"][0].split(" ")

    assert "https://www.googleapis.com/auth/calendar.calendars.readonly" in requested_scopes


def test_build_authorization_url_strips_pkce_params() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())

    url = integration.build_authorization_url(state=None)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    assert "code_challenge" not in query
    assert "code_challenge_method" not in query


def test_build_authorization_url_includes_state() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())

    url = integration.build_authorization_url(state="csrf-token-value")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    assert query["state"] == ["csrf-token-value"]


def test_exchange_code_for_tokens_returns_token_payload() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())

    fake_flow_credentials = MagicMock()
    fake_flow_credentials.token = "access-token-value"
    fake_flow_credentials.refresh_token = "refresh-token-value"
    fake_flow_credentials.client_id = "test-client-id"
    fake_flow_credentials.client_secret = "test-client-secret"
    fake_flow_credentials.scopes = ["https://www.googleapis.com/auth/calendar.events"]
    fake_flow_credentials.expiry = datetime(2026, 8, 21, 12, 0, 0)
    fake_flow_credentials.id_token = "id-token-value"

    fake_flow = MagicMock()
    fake_flow.credentials = fake_flow_credentials

    with patch(
        "app.integrations.google_auth.Flow.from_client_config", return_value=fake_flow
    ):
        result = integration.exchange_code_for_tokens(code="auth-code", state="state-value")

    fake_flow.fetch_token.assert_called_once_with(code="auth-code")
    assert result["access_token"] == "access-token-value"
    assert result["refresh_token"] == "refresh-token-value"
    assert result["client_id"] == "test-client-id"
    assert result["client_secret"] == "test-client-secret"
    assert result["scopes"] == ["https://www.googleapis.com/auth/calendar.events"]
    assert result["expiry"] == "2026-08-21T12:00:00"
    assert result["id_token"] == "id-token-value"
    assert result["state"] == "state-value"


def test_exchange_code_for_tokens_handles_missing_expiry() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())

    fake_flow_credentials = MagicMock()
    fake_flow_credentials.token = "access-token-value"
    fake_flow_credentials.refresh_token = None
    fake_flow_credentials.client_id = "test-client-id"
    fake_flow_credentials.client_secret = "test-client-secret"
    fake_flow_credentials.scopes = []
    fake_flow_credentials.expiry = None
    fake_flow_credentials.id_token = None

    fake_flow = MagicMock()
    fake_flow.credentials = fake_flow_credentials

    with patch(
        "app.integrations.google_auth.Flow.from_client_config", return_value=fake_flow
    ):
        result = integration.exchange_code_for_tokens(code="auth-code", state=None)

    assert result["expiry"] is None
    assert result["refresh_token"] is None
    assert result["state"] is None


def test_build_credentials_constructs_credentials_object() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())
    tokens = {
        "access_token": "access-token-value",
        "refresh_token": "refresh-token-value",
        "client_id": "token-client-id",
        "client_secret": "token-client-secret",
        "scopes": ["https://www.googleapis.com/auth/calendar.events"],
        "expiry": None,
    }

    credentials = integration.build_credentials(tokens)

    assert isinstance(credentials, Credentials)
    assert credentials.token == "access-token-value"
    assert credentials.refresh_token == "refresh-token-value"
    assert credentials.client_id == "token-client-id"
    assert credentials.client_secret == "token-client-secret"
    assert credentials.token_uri == "https://oauth2.googleapis.com/token"
    assert credentials.scopes == ["https://www.googleapis.com/auth/calendar.events"]


def test_refresh_credentials_calls_refresh_and_returns_same_object() -> None:
    integration = GoogleOAuthIntegration(settings=make_settings())
    fake_credentials = MagicMock()

    with patch("app.integrations.google_auth.Request") as mock_request_cls:
        result = integration.refresh_credentials(fake_credentials)

    fake_credentials.refresh.assert_called_once_with(mock_request_cls.return_value)
    assert result is fake_credentials