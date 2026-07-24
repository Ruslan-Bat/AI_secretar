"""Ожидаемые ошибки операций с календарём."""


class CalendarError(RuntimeError):
    """Базовая ожидаемая ошибка календаря."""


class CalendarInputError(CalendarError):
    """Возникает при неверном формате календарной команды Telegram."""


class CalendarIntegrationError(CalendarError):
    """Возникает, если Google Calendar не может выполнить операцию."""
