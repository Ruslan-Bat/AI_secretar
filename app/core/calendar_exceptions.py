"""Ожидаемые ошибки операций с календарём."""


class CalendarError(RuntimeError):
    """Базовая ожидаемая ошибка календаря."""


class CalendarInputError(CalendarError):
    """Возникает при неверном формате календарной команды Telegram."""


class CalendarIntegrationError(CalendarError):
    """Возникает, если Google Calendar не может выполнить операцию."""


class CalendarAuthRequiredError(CalendarError):
    """Возникает, если у пользователя нет активной OAuth-связи с Google."""


class CalendarTokenRefreshError(CalendarError):
    """Возникает, если не удалось обновить access token пользователя."""
