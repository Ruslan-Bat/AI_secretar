"""Интеграция с Google OAuth 2.0."""

from __future__ import annotations
import urllib.parse
from typing import Any

from datetime import datetime

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import Settings

# Указываем oauthlib игнорировать изменение скоупов (добавление openid от Google)
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'


class GoogleOAuthIntegration:
    """Оборачивает Google OAuth 2.0 для локальной разработки."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client_id = settings.GOOGLE_CLIENT_ID or ""
        self._client_secret = settings.GOOGLE_CLIENT_SECRET or ""
        self._redirect_uri = settings.GOOGLE_REDIRECT_URI or "http://localhost:8000/auth/google/callback"
        self._scopes = [
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.calendars.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ]

    def build_authorization_url(self, state: str | None = None) -> str:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self._redirect_uri],
                }
            },
            scopes=self._scopes,
        )
        flow.redirect_uri = self._redirect_uri
        
        # Библиотека автоматически сгенерирует URL с PKCE-параметрами
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",  # Запрашиваем refresh token каждый раз
        )
        
        # Принудительно вырезаем PKCE-параметры из ссылки
        parsed_url = urllib.parse.urlparse(authorization_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        query_params.pop("code_challenge", None)
        query_params.pop("code_challenge_method", None)
        
        # Собираем чистую ссылку обратно
        clean_query = urllib.parse.urlencode(query_params, doseq=True)
        clean_auth_url = parsed_url._replace(query=clean_query).geturl()
        
        return clean_auth_url

    def exchange_code_for_tokens(self, code: str, state: str | None = None) -> dict[str, Any]:
    

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self._redirect_uri],
                }
            },
            scopes=self._scopes,
        )
        flow.redirect_uri = self._redirect_uri
        flow.fetch_token(code=code)

        credentials = flow.credentials
        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "id_token": getattr(credentials, "id_token", None),
            "state": state,
        }

    def build_credentials(self, tokens: dict[str, Any]) -> Credentials:

        expiry_raw = tokens.get("expiry")
        expiry = None
        if isinstance(expiry_raw, str) and expiry_raw:
            expiry = datetime.fromisoformat(expiry_raw)
        elif isinstance(expiry_raw, datetime):
            expiry = expiry_raw

        return Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            token_uri=tokens.get("token_uri") or "https://oauth2.googleapis.com/token",
            scopes=tokens.get("scopes"),
            expiry=expiry,
        )

    def refresh_credentials(self, credentials: Credentials) -> Credentials:
        credentials.refresh(Request())
        return credentials
