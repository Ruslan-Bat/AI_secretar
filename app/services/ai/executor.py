"""Слой исполнения инструментов AI-ассистента."""

from pydantic import ValidationError

from app.core.ai_exceptions import ToolArgumentError
from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
    CalendarIntegrationError,
    CalendarTokenRefreshError,
)
from app.domain.ai import CreateEventInput
from app.services.calendar import CalendarService


class ToolExecutor:
    """Выполняет операции, вызываемые через tool calling.

    Контракт execute():
    - Успех (включая ожидаемые бизнес-ошибки вроде "нужна авторизация")
      -> возвращает str с текстом для модели.
    - Невалидные аргументы от модели -> бросает ToolArgumentError.
    Вызывающий код обязан ловить ToolArgumentError отдельно.
    """

    def __init__(self, calendar_service: CalendarService) -> None:
        self._calendar_service = calendar_service

    async def execute(self, tool_name: str, arguments: dict, user_id: int) -> str:
        if tool_name != "create_event":
            return f"Неизвестный инструмент: {tool_name}"

        try:
            payload = CreateEventInput(**arguments)
        except ValidationError as error:
            raise ToolArgumentError(tool_name, error) from error

        command_args = (
            f"{payload.start_date.isoformat()} "
            f"{payload.start_time.strftime('%H:%M')} "
            f"{payload.duration_minutes} {payload.title}"
        )
        try:
            event = await self._calendar_service.create_from_text(command_args, user_id)
        except CalendarInputError as error:
            return f"Ошибка ввода: {error}"
        except CalendarAuthRequiredError:
            return "Пользователь не авторизован в Google Calendar. Попроси пройти /login."
        except CalendarTokenRefreshError:
            return "Не удалось обновить токен Google. Попроси пользователя пройти /login заново."
        except CalendarIntegrationError:
            return "Google Calendar временно недоступен. Предложи попробовать позже."

        return f"Событие успешно создано на {payload.start_date.isoformat()}. ID: {event.event_id}"
