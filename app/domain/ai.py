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