"""Оркестрация диалога DeepSeek с tool calling."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.domain.ai import CreateEventInput
from app.integrations.deepseek import DeepSeekClient
from app.services.ai.executor import ToolExecutor
from app.services.ai.prompts import get_system_prompt


logger = logging.getLogger(__name__)


class AIAgent:
    """Обрабатывает пользовательские сообщения и оркестрирует вызовы инструментов."""

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        tool_executor: ToolExecutor,
    ) -> None:
        self._deepseek_client = deepseek_client
        self._tool_executor = tool_executor

    async def process_message(self, user_id: int, text: str) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": text},
        ]
        tools = [self._create_event_tool_schema()]

        try:
            response = await self._deepseek_client.chat_completion(messages=messages, tools=tools)
        except Exception as error:
            logger.exception("DeepSeek request failed: %s", error)
            return "Не удалось обратиться к ИИ-ассистенту. Попробуйте позже."

        assistant_message = response.choices[0].message
        print("---------------------------------")
        print(assistant_message)
        print("---------------------------------")
        tool_calls = getattr(assistant_message, "tool_calls", None) or []
        if not tool_calls:
            return (assistant_message.content or "").strip() or "Не удалось сформировать ответ."

        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [self._tool_call_to_message(tc) for tc in tool_calls],
            }
        )

        # Agent loop: ассистент запросил инструмент -> выполняем -> возвращаем результат
        # обратно модели, чтобы она сформировала финальный ответ пользователю.
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
                except ValidationError as error:
                    tool_result = (
                        f"Ошибка валидации аргументов: {error}. "
                        "Исправь формат и повтори вызов."
                    )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_result,
                }
            )

        try:
            final_response = await self._deepseek_client.chat_completion(messages=messages, tools=tools)
        except Exception as error:
            logger.exception("DeepSeek follow-up request failed: %s", error)
            return messages[-1]["content"]

        content = final_response.choices[0].message.content or ""
        return content.strip() or "Готово."

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
