"""Сервис для OAuth-потока Google с использованием PostgreSQL."""

from __future__ import annotations

import jwt
from datetime import datetime, timedelta, timezone
from typing import Any

from google.auth.transport import requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials

from app.config import Settings
from app.domain.credentials import GoogleCredentials
from app.integrations.google_auth import GoogleOAuthIntegration
from app.repositories.sql_user import SqlCredentialsRepository 


class GoogleAuthService:
    """Управляет стартом OAuth, обменом кода на токен и сохранением токенов в БД."""

    def __init__(self, settings: Settings, credentials_repo: SqlCredentialsRepository) -> None:
        self._settings = settings
        self._repository = credentials_repo
        self._integration = GoogleOAuthIntegration(settings=settings)
        # Ensure we use a plain str for PyJWT and static type checkers (SecretStr is not acceptable)
        if getattr(settings, "JWT_SECRET", None):
            self._jwt_secret: str = settings.JWT_SECRET.get_secret_value()
        else:
            self._jwt_secret = "change-me-in-production"


    def generate_state_token(self, telegram_id: int) -> str:
        """Генерирует подписанный JWT для параметра state с временем жизни."""
        payload = {
            "telegram_id": telegram_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15) # Токен живет всего 15 минут
        }
        # Шифруем данные с помощью секретного ключа сервера
        return jwt.encode(payload, self._jwt_secret, algorithm="HS256")

    def verify_state_token(self, token: str) -> int:
        """Проверяет JWT, убеждается, что он не подделан и не протух, возвращает telegram_id."""
        try:
            # Расшифровываем. Если кто-то изменил хотя бы 1 символ, выбросится ошибка InvalidTokenError
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            return payload["telegram_id"]
        except jwt.ExpiredSignatureError:
            raise ValueError("Ссылка устарела. Пожалуйста, запросите новую ссылку для авторизации.")
        except jwt.InvalidTokenError:
            raise ValueError("Недействительный токен безопасности. Возможна попытка взлома (CSRF).")

    def build_authorization_url(self, telegram_id: int) -> str:
        """Возвращает URL для перенаправления пользователя на Google."""
        state_token = self.generate_state_token(telegram_id)
        return self._integration.build_authorization_url(state=state_token)

    def _extract_email(self, tokens: dict[str, Any]) -> str | None:
        raw_id_token = tokens.get("id_token")
        client_id = self._settings.GOOGLE_CLIENT_ID
        if not raw_id_token or not client_id:
            return None
        if not isinstance(raw_id_token, str):
            raise ValueError("Google returned an invalid ID token")

        claims = id_token.verify_oauth2_token(
            raw_id_token,
            requests.Request(),
            audience=client_id,
        )
        email = claims.get("email")
        return email if isinstance(email, str) and email else None

    async def exchange_code_for_tokens(self, code: str, telegram_id: int, state: str | None = None) -> GoogleCredentials:
        """
        Обменивает authorization code на access/refresh token и сохраняет в БД.
        Важно: параметр state должен содержать telegram_id пользователя.
        """

        # Получаем "сырые" токены от Google через слой интеграции
        tokens = self._integration.exchange_code_for_tokens(code=code, state=state)
        
        # Парсим время истечения токена, если оно есть
        expiry_str = tokens.get("expiry")
        expires_at = (
            datetime.fromisoformat(expiry_str)
            if isinstance(expiry_str, str) and expiry_str
            else None
        )
        email = self._extract_email(tokens)

        # Формируем доменную модель
        credentials = GoogleCredentials(
            telegram_id=telegram_id,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
            email=email,
        )
        
        # Сохраняем в базу данных (upsert обновит данные, если они уже есть)
        await self._repository.upsert(credentials)
        
        return credentials

    async def get_credentials(self, telegram_id: int) -> GoogleCredentials | None:
        """Загружает сохранённые токены из базы данных по telegram_id."""
        return await self._repository.get_by_telegram_id(telegram_id)

    def build_oauth_credentials(self, db_creds: GoogleCredentials) -> Credentials:
        """
        Преобразует доменную модель из БД в объект google.oauth2.credentials.Credentials,
        который нужен для GoogleCalendarGateway.
        """
        tokens_dict = {
            "access_token": db_creds.access_token,
            "refresh_token": db_creds.refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "client_secret": self._settings.GOOGLE_CLIENT_SECRET,
            "scopes": self._integration._scopes,
        }
        return self._integration.build_credentials(tokens_dict)