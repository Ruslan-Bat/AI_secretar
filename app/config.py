"""Безопасно загружает настройки Telegram, вебхука, Google Calendar и БД из .env."""

from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigurationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Проверенные настройки из файла ``.env`` в корне проекта."""

    BOT_TOKEN: SecretStr | None = None
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    BOT_MODE: Literal["polling", "webhook"] = "polling"
    WEBHOOK_BASE_URL: str | None = None
    WEBHOOK_PATH: str = "/telegram/webhook"
    WEBHOOK_SECRET: SecretStr | None = None
    GOOGLE_CALENDAR_ENABLED: bool = False
    GOOGLE_CALENDAR_TIMEZONE: str = "Europe/Moscow"
    GOOGLE_CALENDAR_MAX_RESULTS: int = Field(default=10, ge=1, le=20)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    USER_REPOSITORY: Literal["memory", "postgres"] = "memory"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = Field(default=5432, ge=1, le=65535)
    DB_USER: str = "postgres"
    DB_PASS: str = "postgres"
    DB_NAME: str = "postgres"
    TESTING: bool = False
    JWT_SECRET: SecretStr = SecretStr("change-me-in-produc5473472tion")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_legacy_debug_value(cls, value: object) -> object:
        """Принимает старые значения DEBUG и уровни логирования."""

        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if normalized in {
            "",
            "1",
            "true",
            "t",
            "on",
            "yes",
            "y",
            "debug",
            "development",
            "dev",
        }:
            return True
        if normalized in {
            "0",
            "false",
            "f",
            "off",
            "no",
            "n",
            "info",
            "warning",
            "error",
            "production",
            "prod",
        }:
            return False
        # Раньше DEBUG мог содержать произвольное значение. Оставляем безопасное
        # значение для разработки, не раскрывая и не переписывая пользовательский .env.
        return True

    @field_validator("BOT_TOKEN", "WEBHOOK_SECRET", mode="before")
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI", mode="before")
    @classmethod
    def empty_google_oauth_setting_is_none(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("DB_HOST", "DB_USER", "DB_PASS", "DB_NAME", mode="before")
    @classmethod
    def normalize_db_string_setting(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("Database settings cannot be empty")
            return stripped
        return value

    @field_validator("WEBHOOK_BASE_URL", mode="before")
    @classmethod
    def normalize_base_url(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value.rstrip("/") or None
        return value

    @field_validator("WEBHOOK_PATH")
    @classmethod
    def normalize_webhook_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("WEBHOOK_PATH cannot be empty")
        return value if value.startswith("/") else f"/{value}"

    @field_validator("GOOGLE_CALENDAR_TIMEZONE")
    @classmethod
    def validate_google_calendar_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown Google Calendar time zone") from None
        return value

    def validate_runtime(self) -> None:
        """Проверяет настройки, необходимые только при реальном запуске бота."""

        if self.TESTING:
            return
        if self.BOT_TOKEN is None or not self.BOT_TOKEN.get_secret_value().strip():
            raise ConfigurationError(
                "BOT_TOKEN is required for a real run; configure it in the project .env"
            )
        if self.BOT_MODE == "webhook" and not self.WEBHOOK_BASE_URL:
            raise ConfigurationError(
                "WEBHOOK_BASE_URL is required when BOT_MODE=webhook"
            )
        if self.GOOGLE_CALENDAR_ENABLED:
            if not self.GOOGLE_CLIENT_ID:
                raise ConfigurationError(
                    "GOOGLE_CLIENT_ID is required when Google Calendar is enabled"
                )
            if not self.GOOGLE_CLIENT_SECRET:
                raise ConfigurationError(
                    "GOOGLE_CLIENT_SECRET is required when Google Calendar is enabled"
                )
            if not self.GOOGLE_REDIRECT_URI:
                raise ConfigurationError(
                    "GOOGLE_REDIRECT_URI is required when Google Calendar is enabled"
                )

    def telegram_token(self) -> str:
        if self.BOT_TOKEN is None:
            raise ConfigurationError("BOT_TOKEN is required for a real run")
        return self.BOT_TOKEN.get_secret_value()

    def webhook_secret(self) -> str | None:
        if self.WEBHOOK_SECRET is None:
            return None
        return self.WEBHOOK_SECRET.get_secret_value()


    def database_url_asyncpg(self) -> str:
        user = quote_plus(self.DB_USER)
        password = quote_plus(self.DB_PASS)
        host = self.DB_HOST.strip()
        database = self.DB_NAME.strip()
        return (
            f"postgresql+asyncpg://{user}:{password}@{host}:{self.DB_PORT}/{database}"
        )


def load_settings() -> Settings:
    """Загружает настройки, не выводя детали проверки и секреты в логи."""

    try:
        return Settings()
    except ValidationError:
        raise ConfigurationError(
            "Invalid application configuration; check the project .env values"
        ) from None
