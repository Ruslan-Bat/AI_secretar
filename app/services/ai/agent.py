"""Оркестрация диалога DeepSeek с tool calling."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from app.core.ai_exceptions import ToolArgumentError, UnknownToolError
from app.domain.ai import (
    CreateEventInput,
    GetEventsInput,
    GetFreeSlotsInput,
    MoveEventInput,
)
from app.integrations.deepseek import DeepSeekClient
from app.services.ai.executor import ToolExecutor
from app.services.ai.prompts import get_system_prompt


logger = logging.getLogger(__name__)

_MAX_AGENT_ITERATIONS: int = 6


@runtime_checkable
class TimeZoneProvider(Protocol):
    async def get_user_time_zone(self, telegram_id: int) -> str | None: ...


@runtime_checkable
class ConversationMemory(Protocol):
    async def get_recent_pairs(self, user_id: int) -> list[tuple[str, str]]: ...

    async def append_pair(self, user_id: int, user_text: str, assistant_text: str) -> None: ...


def _format_validation_feedback(error: ToolArgumentError) -> str:
    return (
        f"Ошибка валидации аргументов инструмента '{error.tool_name}': "
        f"{error.original.errors()!r}. Исправь формат и повтори вызов."
    )


class AIAgent:
    """Обрабатывает пользовательские сообщения и оркестрирует вызовы инструментов."""

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        tool_executor: ToolExecutor,
        time_zone_provider: TimeZoneProvider | None = None,
        default_time_zone: str = "UTC",
        memory: ConversationMemory | None = None,
    ) -> None:
        self._deepseek_client = deepseek_client
        self._tool_executor = tool_executor
        self._time_zone_provider = time_zone_provider
        self._default_time_zone = default_time_zone
        self._memory = memory
        self._tools = self._build_tool_schemas()

    async def process_message(self, user_id: int, text: str) -> str:
        time_zone = await self._resolve_time_zone(user_id)
        history = await self._load_history(user_id)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": get_system_prompt(time_zone)}
        ]
        for past_user_text, past_assistant_text in history:
            messages.append({"role": "user", "content": past_user_text})
            messages.append({"role": "assistant", "content": past_assistant_text})
        messages.append({"role": "user", "content": text})

        for iteration in range(1, _MAX_AGENT_ITERATIONS + 1):
            try:
                response = await self._deepseek_client.chat_completion(
                    messages=messages, tools=self._tools
                )
            except Exception as error:
                logger.exception(
                    "DeepSeek request failed (iteration=%s): %s", iteration, error
                )
                return "Не удалось обратиться к ИИ-ассистенту. Попробуйте позже."

            assistant_message = response.choices[0].message
            logger.debug(
                "Assistant message (iteration=%s): %r", iteration, assistant_message
            )

            tool_calls = getattr(assistant_message, "tool_calls", None) or []
            if not tool_calls:
                content = (assistant_message.content or "").strip()
                result = content or "Не удалось сформировать ответ."
                await self._remember(user_id, text, result)
                return result

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [self._tool_call_to_message(tc) for tc in tool_calls],
                }
            )

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": await self._run_tool_call(tool_call, user_id),
                    }
                )

        logger.warning(
            "Agent loop exceeded max iterations (%s) for user_id=%s",
            _MAX_AGENT_ITERATIONS,
            user_id,
        )
        return (
            "Не удалось завершить обработку запроса за отведённое число шагов. "
            "Проверьте календарь: часть изменений могла быть применена."
        )

    async def _run_tool_call(self, tool_call: Any, user_id: int) -> str:
        """Выполняет один tool call и всегда возвращает текст для модели."""
        tool_name = tool_call.function.name
        raw_arguments = tool_call.function.arguments or "{}"

        try:
            parsed_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as error:
            return f"Ошибка в аргументах инструмента: невалидный JSON ({error})."

        if not isinstance(parsed_arguments, dict):
            parsed_arguments = {}

        try:
            return await self._tool_executor.execute(tool_name, parsed_arguments, user_id)
        except ToolArgumentError as error:
            return _format_validation_feedback(error)
        except UnknownToolError as error:
            logger.warning(
                "Model requested unknown tool: %s (user_id=%s)", error.tool_name, user_id
            )
            return (
                f"Инструмент '{error.tool_name}' не существует. "
                "Проверь название и вызови снова."
            )
        except Exception:
            logger.exception(
                "Unexpected error executing tool '%s' (user_id=%s)", tool_name, user_id
            )
            return (
                f"Внутренняя ошибка при выполнении инструмента '{tool_name}'. "
                "Не вызывай его повторно — сообщи пользователю, что операция "
                "не выполнена, и предложи попробовать позже."
            )

    async def _resolve_time_zone(self, user_id: int) -> str:
        if self._time_zone_provider is None:
            return self._default_time_zone
        try:
            stored = await self._time_zone_provider.get_user_time_zone(user_id)
        except Exception:
            logger.warning(
                "Failed to resolve time zone for user_id=%s", user_id, exc_info=True
            )
            return self._default_time_zone
        return stored or self._default_time_zone

    async def _load_history(self, user_id: int) -> list[tuple[str, str]]:
        if self._memory is None:
            return []
        try:
            return await self._memory.get_recent_pairs(user_id)
        except Exception:
            logger.warning(
                "Failed to load conversation memory for user_id=%s", user_id, exc_info=True
            )
            return []

    async def _remember(self, user_id: int, user_text: str, assistant_text: str) -> None:
        if self._memory is None:
            return
        try:
            await self._memory.append_pair(user_id, user_text, assistant_text)
        except Exception:
            logger.warning(
                "Failed to store conversation memory for user_id=%s", user_id, exc_info=True
            )

    @staticmethod
    def _build_tool_schemas() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_event",
                    "description": (
                        "Создаёт новое событие в Google Calendar пользователя. "
                        "Используй, когда нужно записать в календарь что-то новое. "
                        "Не используй для изменения уже существующего события — "
                        "для этого есть move_event."
                    ),
                    "parameters": CreateEventInput.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_events",
                    "description": (
                        "Показывает, что уже запланировано в календаре за диапазон дней. "
                        "Используй, когда пользователь спрашивает о своих планах, "
                        "а также перед move_event, чтобы узнать настоящий ID события. "
                        "Возвращает названия, время и ID событий."
                    ),
                    "parameters": GetEventsInput.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_free_slots",
                    "description": (
                        "Ищет свободные окна в календаре нужной длительности. "
                        "Используй, когда нужно подобрать время для новой встречи "
                        "или проверить, свободно ли время перед созданием события. "
                        "Возвращает только промежутки, не занятые событиями."
                    ),
                    "parameters": GetFreeSlotsInput.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "move_event",
                    "description": (
                        "Переносит существующее событие на новое время, сохраняя "
                        "его название и остальные детали. Требует настоящий ID "
                        "события — получи его через get_events, никогда не выдумывай. "
                        "Перед вызовом назови пользователю событие и новое время "
                        "и дождись подтверждения."
                    ),
                    "parameters": MoveEventInput.model_json_schema(),
                },
            },
        ]

    @staticmethod
    def _tool_call_to_message(tool_call: Any) -> dict[str, Any]:
        return {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            },
        }