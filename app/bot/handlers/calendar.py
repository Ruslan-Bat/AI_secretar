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
    EventNotFoundError,
)
from app.domain.calendar_event import CalendarEvent
from app.services.calendar import CalendarService


NOT_CONFIGURED_MESSAGE = (
    "Google Calendar пока не настроен. Включите интеграцию и пройдите /login."
)
UNAVAILABLE_MESSAGE = "Не удалось обратиться к Google Calendar. Попробуйте позже."


def _format_start(value: datetime | date) -> str:
    if isinstance(value, datetime):
        zone = f" ({value.tzname()})" if value.tzinfo is not None else ""
        return value.strftime("%d.%m.%Y %H:%M") + zone
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

    from_user = getattr(message, "from_user", None)
    telegram_id = from_user.id if from_user is not None else None

    try:
       events = await calendar_service.list_upcoming(telegram_id=telegram_id)
    except CalendarAuthRequiredError:
       await message.answer("Нужно пройти /login")
       return
    except CalendarTokenRefreshError:
       await message.answer("Не удалось обновить токен")
       return
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


async def handle_today(
    message: Message,
    calendar_service: CalendarService | None,
) -> None:
    """Показывает события пользователя только за сегодняшний день."""
    if calendar_service is None:
        await message.answer(NOT_CONFIGURED_MESSAGE)
        return

    from_user = getattr(message, "from_user", None)

    try:
        if from_user is None:
            raise CalendarAuthRequiredError("Нужно пройти /login")
        events = await calendar_service.get_events(
            start_day_offset=0,
            end_day_offset=0,
            telegram_id=from_user.id,
        )
    except CalendarAuthRequiredError:
        await message.answer("Нужно пройти /login")
        return
    except CalendarTokenRefreshError:
        await message.answer("Не удалось обновить токен")
        return
    except CalendarIntegrationError:
        await message.answer(UNAVAILABLE_MESSAGE)
        return

    if not events:
        await message.answer("На сегодня событий нет.")
        return

    messages = ["События на сегодня:"]
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
            raise CalendarAuthRequiredError("Нужно пройти /login")
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


async def handle_timezone(
    message: Message,
    command: CommandObject,
    calendar_service: CalendarService | None,
) -> None:
    """Показывает или сохраняет часовой пояс пользователя."""
    if message.chat.type != "private":
        await message.answer("Настройте часовой пояс в личном чате с ботом.")
        return
    if calendar_service is None:
        await message.answer(NOT_CONFIGURED_MESSAGE)
        return
    from_user = getattr(message, "from_user", None)
    if from_user is None:
        await message.answer("Нужно пройти /login")
        return
    try:
        time_zone = (command.args or "").strip()
        if not time_zone:
            time_zone = await calendar_service.get_time_zone(from_user.id)
            await message.answer(
                f"Ваш часовой пояс: {time_zone}\n"
                "Изменить: /timezone Europe/Moscow"
            )
            return
        time_zone = await calendar_service.set_time_zone(from_user.id, time_zone)
    except CalendarInputError as error:
        await message.answer(str(error))
        return
    except CalendarAuthRequiredError:
        await message.answer("Нужно пройти /login")
        return
    await message.answer(
        f"Часовой пояс установлен: {time_zone}.\n"
        "Новые события и ответы используют этот пояс. "
        "Уже созданные события не переносятся."
    )


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
            raise CalendarAuthRequiredError("Нужно пройти /login")
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
    except EventNotFoundError:
        await message.answer("Не удалось найти событие с таким ID")
        return

    await message.answer("Событие удалено из Google Calendar.")


def create_router() -> Router:
    router = Router(name="calendar")
    router.message.register(handle_calendar, Command("calendar"))
    router.message.register(handle_today, Command("today"))
    router.message.register(handle_timezone, Command("timezone"))
    router.message.register(handle_add_event, Command("add_event"))
    router.message.register(handle_delete_event, Command("delete_event"))
    return router
