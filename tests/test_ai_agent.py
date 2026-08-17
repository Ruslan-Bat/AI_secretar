from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain.ai import CreateEventInput
from app.services.ai.agent import AIAgent


def _chat_response(content: str | None, tool_calls: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls),
            )
        ]
    )


def _tool_call(name: str, arguments: str, call_id: str = "call_1") -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _sample_validation_error() -> ValidationError:
    try:
        CreateEventInput.model_validate({})
    except ValidationError as error:
        return error
    raise AssertionError("Expected ValidationError")


@pytest.mark.asyncio
async def test_process_message_returns_plain_text_without_tool_calls() -> None:
    deepseek_client = SimpleNamespace(
        chat_completion=AsyncMock(return_value=_chat_response("Привет! Чем помочь?"))
    )
    tool_executor = SimpleNamespace(execute=AsyncMock())
    agent = AIAgent(deepseek_client=deepseek_client, tool_executor=tool_executor)

    result = await agent.process_message(user_id=101, text="Привет")

    assert result == "Привет! Чем помочь?"
    deepseek_client.chat_completion.assert_awaited_once()
    tool_executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_message_executes_tool_and_returns_follow_up_answer() -> None:
    call = _tool_call(
        name="create_event",
        arguments='{"title":"Созвон","date":"2026-08-18","start_time":"10:00","duration_minutes":30}',
    )
    deepseek_client = SimpleNamespace(
        chat_completion=AsyncMock(
            side_effect=[
                _chat_response(content="", tool_calls=[call]),
                _chat_response(content="Готово! Создал событие на завтра."),
            ]
        )
    )
    tool_executor = SimpleNamespace(
        execute=AsyncMock(return_value="Событие успешно создано на 2026-08-18")
    )
    agent = AIAgent(deepseek_client=deepseek_client, tool_executor=tool_executor)

    result = await agent.process_message(user_id=777, text="Создай созвон завтра в 10:00 на 30 минут")

    assert result == "Готово! Создал событие на завтра."
    tool_executor.execute.assert_awaited_once_with(
        "create_event",
        {
            "title": "Созвон",
            "date": "2026-08-18",
            "start_time": "10:00",
            "duration_minutes": 30,
            "_user_id": 777,
        },
    )
    assert deepseek_client.chat_completion.await_count == 2


@pytest.mark.asyncio
async def test_process_message_handles_tool_validation_error_and_continues_loop() -> None:
    call = _tool_call(
        name="create_event",
        arguments='{"title":"Созвон","date":"bad-date","start_time":"10:00","duration_minutes":30}',
    )
    deepseek_client = SimpleNamespace(
        chat_completion=AsyncMock(
            side_effect=[
                _chat_response(content="", tool_calls=[call]),
                _chat_response(content="Исправил формат. Уточните дату в YYYY-MM-DD."),
            ]
        )
    )
    tool_executor = SimpleNamespace(
        execute=AsyncMock(side_effect=_sample_validation_error())
    )
    agent = AIAgent(deepseek_client=deepseek_client, tool_executor=tool_executor)

    result = await agent.process_message(user_id=42, text="Создай событие")

    assert result == "Исправил формат. Уточните дату в YYYY-MM-DD."
    second_call_messages = deepseek_client.chat_completion.await_args_list[1].kwargs["messages"]
    tool_message = second_call_messages[-1]
    assert tool_message["role"] == "tool"
    assert "Ошибка валидации аргументов" in tool_message["content"]
