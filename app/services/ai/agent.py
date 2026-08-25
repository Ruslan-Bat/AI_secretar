"""Оркестрация диалога DeepSeek с tool calling."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from app.core.ai_exceptions import ToolArgumentError, UnknownToolError

from app.domain.ai import CreateEventInput
from app.integrations.deepseek import DeepSeekClient
from app.services.ai.executor import ToolExecutor
from app.services.ai.prompts import get_system_prompt


logger = logging.getLogger(__name__)

_MAX_AGENT_ITERATIONS: int = 3


def _format_validation_feedback(error: ToolArgumentError) -> str:
    return (
        f"Ошибка валидации аргументов инструмента '{error.tool_name}': "
        f"{error.original.errors()!r}. Исправь формат и повтори вызов."
    )

@runtime_checkable
class ConversationMemory(Protocol):
    async def get_recent_pairs(self, user_id: int) -> list[tuple[str, str]]:
        """Возвращает пары (user_text, assistant_text) в хронологическом порядке (старые → новые)."""
        ...

@runtime_checkable
class TimeZoneProvider(Protocol):
    #Лучше этот протокол, чем импортировать класс. Легче тестить.
    async def get_user_time_zone(self, telegram_id: int) -> str | None: 
        ...


class AIAgent:
    """Обрабатывает пользовательские сообщения и оркестрирует вызовы инструментов."""

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        tool_executor: ToolExecutor,
        time_zone_provider: TimeZoneProvider | None = None,
        default_time_zone: str = "UTC",
    ) -> None:
        self._deepseek_client = deepseek_client
        self._tool_executor = tool_executor
        self._time_zone_provider = time_zone_provider
        self._default_time_zone = default_time_zone

    async def _resolve_time_zone(self, user_id: int) -> str:
        if self._time_zone_provider is None:
            return self._default_time_zone
        try:
            stored = await self._time_zone_provider.get_user_time_zone(user_id)
        except Exception:
            logger.warning("Failed to resolve time zone for user_id=%s", user_id, exc_info=True)
            return self._default_time_zone
        return stored or self._default_time_zone

    async def process_message(self, user_id: int, text: str) -> str:
        time_zone = await self._resolve_time_zone(user_id)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": get_system_prompt(time_zone=time_zone)},
            {"role": "user", "content": text},
        ]
        tools = [self._create_event_tool_schema()]

        #Agent loop: модель может вызывать инструменты несколько раз, пока не сформирует финальный ответ.
        for iteration in range(1, _MAX_AGENT_ITERATIONS + 1):

            try:
                response = await self._deepseek_client.chat_completion(messages=messages, tools=tools)
            except Exception as error:
                logger.exception("DeepSeek request failed (iteration=%s): %s", iteration, error)
                return "Не удалось обратиться к ИИ-ассистенту. Попробуйте позже."

            assistant_message = response.choices[0].message
            logger.debug("Assistant message (iteration=%s): %r", iteration, assistant_message)

            tool_calls = getattr(assistant_message, "tool_calls", None) or []
            if not tool_calls:
                content = (assistant_message.content or "").strip()
                return content or "Не удалось сформировать ответ."

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [self._tool_call_to_message(tc) for tc in tool_calls],
                }
            )


            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                raw_arguments = tool_call.function.arguments or "{}"
                try:
                    parsed_arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as error:
                    tool_result = f"Ошибка в аргументах инструмента: невалидный JSON ({error})."
                else:
                    if not isinstance(parsed_arguments, dict):
                        parsed_arguments = {}

                    try:
                        tool_result = await self._tool_executor.execute(tool_name, parsed_arguments, user_id)
                    except ToolArgumentError  as error:
                        tool_result = _format_validation_feedback(error)
                    except UnknownToolError as error:
                        logger.warning("Model requested unknown tool: %s (user_id=%s)", error.tool_name, user_id)
                        tool_result = (
                            f"Инструмент '{error.tool_name}' не существует. "
                            "Проверь название, а затем вызови снова."
                        )
                    except Exception as error:
                        logger.exception(
                            "Unexpected error executing tool '%s' (user_id=%s): %s",
                            tool_name,
                            user_id,
                            error,
                        )
                        tool_result = (
                            f"Внутренняя ошибка при выполнении инструмента '{tool_name}'. "
                            "Не пытайся вызывать его снова в этом же ответе — сообщи "
                            "пользователю, что операция не выполнена, и предложи попробовать позже."
                        )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_result,
                    }
                )

        logger.warning(
            "Agent loop exceeded max iterations (%s) for user_id=%s",
            _MAX_AGENT_ITERATIONS,
            user_id,
        )

        return (
            "Не удалось завершить обработку запроса за отведённое число шагов. "
            "Если вы просили создать событие — проверьте календарь: "
            "оно могло быть создано, даже если ответ не пришёл."
        )
    
    def _create_event_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "create_event",
                "description": "Создает событие в Google Calendar пользователя.",
                "parameters": CreateEventInput.model_json_schema(),
            },
        }    
    
   

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

