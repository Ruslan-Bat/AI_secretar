"""Команды просмотра, создания и удаления событий без LLM-разбора."""

from datetime import date, datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.core.calendar_exceptions import (
    CalendarAuthRequiredError,
    CalendarInputError,
    CalendarIntegrationError,
    CalendarTokenRefreshError,
)
from app.domain.calendar_event import CalendarEvent
from app.services.calendar import CalendarService


NOT_CONFIGURED_MESSAGE = (
    "Google Calendar пока не настроен. Включите интеграцию и заполните "
    "GOOGLE_SERVICE_ACCOUNT_FILE и GOOGLE_CALENDAR_ID."
)
UNAVAILABLE_MESSAGE = "Не удалось обратиться к Google Calendar. Попробуйте позже."


def _format_start(value: datetime | date) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return value.strftime("%d.%m.%Y (весь день)")


def _format_event(event: CalendarEvent, number: int | None = None) -> str:
    prefix = f"{number}. " if number is not None else ""
    title = " ".join(event.title.split())[:120]
    return f"{prefix}{_format_start(event.start)} — {title}\nID: {event.event_id}"


async def handle_calendar(
    message: Message,
    calendar_service: CalendarService | None,
) -> None:
    if calendar_service is None:
        await message.answer(NOT_CONFIGURED_MESSAGE)
        return

    try:
        events = await calendar_service.list_upcoming()
    except CalendarIntegrationError:
        await message.answer(UNAVAILABLE_MESSAGE)
        return

    if not events:
        await message.answer("Предстоящих событий не найдено.")
        return

    messages = ["Ближайшие события Google Calendar:"]
    for number, event in enumerate(events, 1):
        event_text = _format_event(event, number)
        candidate = messages[-1] + "\n\n" + event_text
        if len(candidate) <= 4000:
            messages[-1] = candidate
        else:
            messages.append(event_text)
    for response in messages:
        await message.answer(response)


async def handle_add_event(
    message: Message,
    command: CommandObject,
    calendar_service: CalendarService | None,
) -> None:
    if calendar_service is None:
        await message.answer(NOT_CONFIGURED_MESSAGE)
        return

    from_user = getattr(message, "from_user", None)

    try:
        if from_user is None:
            event = await calendar_service.create_from_text(command.args)
        else:
            event = await calendar_service.create_from_text(command.args, from_user.id)
    except CalendarInputError as error:
        await message.answer(str(error))
        return
    except CalendarAuthRequiredError:
        await message.answer("Нужно пройти /login")
        return
    except CalendarTokenRefreshError:
        await message.answer("Не удалось обновить токен")
        return
    except CalendarIntegrationError:
        await message.answer("Не удалось обратиться к Google Calendar")
        return

    await message.answer("Событие добавлено в Google Calendar:\n" + _format_event(event))


async def handle_delete_event(
    message: Message,
    command: CommandObject,
    calendar_service: CalendarService | None,
) -> None:
    if calendar_service is None:
        await message.answer(NOT_CONFIGURED_MESSAGE)
        return

    from_user = getattr(message, "from_user", None)

    try:
        if from_user is None:
            await calendar_service.delete_from_text(command.args)
        else:
            await calendar_service.delete_from_text(command.args, from_user.id)
    except CalendarInputError as error:
        await message.answer(str(error))
        return
    except CalendarAuthRequiredError:
        await message.answer("Нужно пройти /login")
        return
    except CalendarTokenRefreshError:
        await message.answer("Не удалось обновить токен")
        return
    except CalendarIntegrationError:
        await message.answer("Не удалось обратиться к Google Calendar")
        return

    await message.answer("Событие удалено из Google Calendar.")


def create_router() -> Router:
    router = Router(name="calendar")
    router.message.register(handle_calendar, Command("calendar"))
    router.message.register(handle_add_event, Command("add_event"))
    router.message.register(handle_delete_event, Command("delete_event"))
    return router
