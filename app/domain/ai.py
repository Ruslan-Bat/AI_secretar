"""Схемы аргументов для tool calling ИИ-ассистента."""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field


class CreateEventInput(BaseModel):
    """Аргументы инструмента создания события календаря.

    Валидируется не только набор полей, но и содержимое: типы
    date/time заставляют Pydantic строго парсить ISO-формат
    (YYYY-MM-DD и HH:MM[:SS]), а не принимать произвольную строку.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: str = Field(
        min_length=1,
        max_length=200,
        description="Название события календаря.",
    )
    start_date: date = Field(
        description="Дата события в формате YYYY-MM-DD (ISO 8601).",
    )
    start_time: time = Field(
        description="Время начала в 24-часовом формате HH:MM.",
    )
    duration_minutes: int = Field(
        gt=0,
        le=24 * 60,
        description="Длительность события в минутах. От 1 до 1440 (не более суток).",
    )


class GetEventsInput(BaseModel):
    """Аргументы инструмента просмотра событий за диапазон дней."""

    model_config = ConfigDict(extra="forbid")

    start_day_offset: int = Field(
        default=0,
        ge=-31,
        le=31,
        description=(
            "Начало диапазона в днях относительно сегодня. "
            "0 — сегодня, 1 — завтра, -1 — вчера."
        ),
    )
    end_day_offset: int = Field(
        default=1,
        ge=-31,
        le=31,
        description=(
            "Конец диапазона в днях относительно сегодня, включительно. "
            "Не может быть меньше start_day_offset."
        ),
    )

class GetFreeSlotsInput(BaseModel):
    """Аргументы инструмента поиска свободных окон в календаре."""

    model_config = ConfigDict(extra="forbid")

    start_day_offset: int = Field(
        default=0,
        ge=-31,
        le=31,
        description=(
            "Начало диапазона поиска в днях относительно сегодня. "
            "0 — сегодня, 1 — завтра."
        ),
    )
    end_day_offset: int = Field(
        default=1,
        ge=-31,
        le=31,
        description=(
            "Конец диапазона поиска в днях относительно сегодня, включительно. "
            "Не может быть меньше start_day_offset."
        ),
    )
    min_duration_minutes: int = Field(
        default=30,
        gt=0,
        le=24 * 60,
        description=(
            "Минимальная длительность свободного окна в минутах. "
            "Окна короче указанной длительности не возвращаются."
        ),
    )

class MoveEventInput(BaseModel):
    """Аргументы инструмента переноса существующего события."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    event_id: str = Field(
        min_length=1,
        max_length=1024,
        pattern=r"^\S+$",
        description=(
            "Идентификатор события из Google Calendar. "
            "Должен быть получен через get_events, а не придуман."
        ),
    )
    new_date: date = Field(
        description="Новая дата события в формате YYYY-MM-DD (ISO 8601).",
    )
    new_time: time = Field(
        description="Новое время начала в 24-часовом формате HH:MM.",
    )
    duration_minutes: int = Field(
        gt=0,
        le=24 * 60,
        description="Длительность события в минутах. От 1 до 1440 (не более суток).",
    )