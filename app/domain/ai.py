"""Схемы аргументов для tool calling ИИ-ассистента."""

from pydantic import BaseModel, Field


class CreateEventInput(BaseModel):
    """Аргументы инструмента создания события календаря."""

    title: str = Field(description="Название события календаря.")
    date: str = Field(description="Дата события в формате YYYY-MM-DD.")
    start_time: str = Field(description="Время начала в формате HH:MM.")
    duration_minutes: int = Field(description="Длительность события в минутах.")
