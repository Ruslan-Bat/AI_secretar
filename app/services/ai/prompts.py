"""Системный промпт ИИ-ассистента."""

from datetime import datetime


_WEEKDAY_RU: dict[int, str] = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}


def get_system_prompt() -> str:
    now = datetime.now() 
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    weekday = _WEEKDAY_RU[now.weekday()]
    return (
        "Ты умный помощник, который управляет календарем пользователя.\n"
        "Текущая локальная дата и время:\n"
        f"- Дата: {current_date}\n"
        f"- День недели: {weekday}\n"
        f"- Время: {current_time}\n\n"
        "Когда пользователь просит создать событие, используй инструмент create_event.\n"
        "Перед вызовом инструмента проверь, что дата строго в формате YYYY-MM-DD, "
        "время в формате HH:MM, а длительность в минутах."
    )
