"""Единая точка внедрения зависимостей для пользователей и Google Calendar."""

from dataclasses import dataclass

from app.config import Settings
from app.integrations.calendar import CalendarGateway
from app.integrations.google_calendar import GoogleCalendarGateway
from app.repositories.memory_user import MemoryUserRepository
from app.repositories.sql_user import SqlCredentialsRepository, SqlUserRepository
from app.repositories.user import UserRepository
from app.services.calendar import CalendarService
from app.services.google_auth import GoogleAuthService
from app.services.user import UserService


@dataclass(slots=True)
class AppContainer:
    user_repository: UserRepository
    user_service: UserService
    calendar_gateway: CalendarGateway | None
    calendar_service: CalendarService | None
    auth_service: GoogleAuthService | None  # Добавлено поле для сервиса авторизации


def build_container(
    settings: Settings | None = None,
    user_repository: UserRepository | None = None,
    calendar_gateway: CalendarGateway | None = None,
) -> AppContainer:

    if user_repository is not None:
        repository = user_repository
    elif settings is not None and settings.USER_REPOSITORY == "postgres":
        repository = SqlUserRepository(settings.database_url_asyncpg())
    else:
        repository = MemoryUserRepository()
        
    gateway = calendar_gateway
    # Клиент Google создаётся лениво и не читает учётные данные при импорте.
    if gateway is None and settings is not None and settings.GOOGLE_CALENDAR_ENABLED:
        gateway = GoogleCalendarGateway(
            credentials_file=settings.google_service_account_path(),
            calendar_id=settings.GOOGLE_CALENDAR_ID or "",
            time_zone=settings.GOOGLE_CALENDAR_TIMEZONE,
        )

    # Инициализация auth_service
    auth_service = None
    if settings is not None:
        auth_service = get_google_auth_service(settings)

    calendar_service = None
    if gateway is not None:
        calendar_service = CalendarService(
            gateway,
            time_zone=(
                settings.GOOGLE_CALENDAR_TIMEZONE
                if settings is not None
                else "Europe/Moscow"
            ),
            max_results=(
                settings.GOOGLE_CALENDAR_MAX_RESULTS if settings is not None else 10
            ),
            auth_service=auth_service,
        )

    return AppContainer(
        user_repository=repository,
        user_service=UserService(repository),
        calendar_gateway=gateway,
        calendar_service=calendar_service,
        auth_service=auth_service,  # Прокидываем в контейнер
    )


def get_google_auth_service(settings: Settings | None = None) -> GoogleAuthService:
    resolved_settings = settings if settings is not None else Settings()
    credentials_repository = SqlCredentialsRepository(
        database_url=resolved_settings.database_url_asyncpg()
    )
    return GoogleAuthService(
        settings=resolved_settings,
        credentials_repo=credentials_repository,
    )