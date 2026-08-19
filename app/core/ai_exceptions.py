"""Исключения ИИ-ассистента (tool calling, agent loop)."""

from __future__ import annotations

from pydantic import ValidationError


class AIAssistantError(Exception):
    """Базовое исключение для всего AI-слоя приложения."""


class ToolExecutionError(AIAssistantError):
    """Базовая ошибка исполнения инструмента ИИ.

    Часть публичного контракта ToolExecutor.execute(): вызывающий код
    обязан ловить это исключение (или его подклассы) отдельно от
    успешного строкового результата.
    """


class ToolArgumentError(ToolExecutionError):
    """Аргументы, присланные моделью, не прошли валидацию Pydantic.

    Оборачивает pydantic.ValidationError, чтобы вызывающий код
    (AIAgent) не был обязан знать, что ToolExecutor использует именно
    Pydantic внутри — это деталь реализации, а не часть контракта.
    """

    def __init__(self, tool_name: str, original: ValidationError) -> None:
        self.tool_name = tool_name
        self.original = original
        super().__init__(f"Невалидные аргументы для '{tool_name}': {original}")
