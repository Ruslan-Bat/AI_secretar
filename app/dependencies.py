"""Единая точка внедрения зависимостей для пользователей и Google Calendar."""

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.integrations.calendar import CalendarGateway
from app.integrations.deepseek import DeepSeekClient
from app.integrations.google_calendar import GoogleCalendarGateway
from app.repositories.memory_user import MemoryUserRepository
from app.repositories.sql_user import SqlCredentialsRepository, SqlUserRepository
from app.repositories.user import UserRepository
from app.services.ai.agent import AIAgent
from app.services.ai.executor import ToolExecutor
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
    ai_agent: AIAgent | None


def build_container(
    settings: Settings | None = None,
    user_repository: UserRepository | None = None,
    calendar_gateway: CalendarGateway | None = None,
) -> AppContainer:

    settings = settings if settings is not None else Settings()

    #Инициализируем БД: Единый движок и пул соединений на всё приложение
    session_factory = None
    if settings.USER_REPOSITORY == "postgres":
        engine = create_async_engine(settings.database_url_asyncpg(), echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

    if user_repository is not None:
        repository = user_repository
    elif session_factory:
        repository = SqlUserRepository(session_factory=session_factory)
    else:
        repository = MemoryUserRepository()
        
    gateway = calendar_gateway
    # Клиент Google создаётся лениво и не читает учётные данные при импорте.
    if gateway is None and settings is not None:
        has_oauth_config = (
            bool(settings.GOOGLE_CLIENT_ID)
            and bool(settings.GOOGLE_CLIENT_SECRET)
            and bool(settings.GOOGLE_REDIRECT_URI)
        )
        if settings.GOOGLE_CALENDAR_ENABLED or has_oauth_config:
            gateway = GoogleCalendarGateway(
                time_zone=settings.GOOGLE_CALENDAR_TIMEZONE,
            )

    # Инициализация auth_service
    auth_service = None
    if session_factory is not None:
        auth_service = build_google_auth_service(settings, session_factory)

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

    ai_agent = None
    if calendar_service is not None and settings.DEEPSEEK_API_KEY is not None:
        deepseek_client = DeepSeekClient(
            api_key=settings.DEEPSEEK_API_KEY.get_secret_value(),
        )
        tool_executor = ToolExecutor(calendar_service)
        ai_agent = AIAgent(
            deepseek_client=deepseek_client,
            tool_executor=tool_executor,
        )

    return AppContainer(
        user_repository=repository,
        user_service=UserService(repository),
        calendar_gateway=gateway,
        calendar_service=calendar_service,
        auth_service=auth_service,
        ai_agent=ai_agent,
    )


def build_google_auth_service(
    settings: Settings,
    session_factory: async_sessionmaker
) -> GoogleAuthService:
    """Создает сервис авторизации, используя общий пул соединений."""
    
    # Репозиторий теперь получает готовую фабрику, а не плодит новые пулы
    credentials_repository = SqlCredentialsRepository(
        session_factory=session_factory
    )

    return GoogleAuthService(
        settings=settings,
        credentials_repo=credentials_repository,
    )


def get_google_auth_service(request: Request) -> GoogleAuthService:
    """Возвращает сервис авторизации из контейнера приложения."""
    container = request.app.state.container
    if container.auth_service is None:
        raise RuntimeError("Google auth service is not configured")
    return container.auth_service