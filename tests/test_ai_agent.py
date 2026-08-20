from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.domain.ai import CreateEventInput
from app.services.ai.agent import AIAgent
from app.integrations.deepseek import DeepSeekClient
from app.services.ai.executor import ToolArgumentError, ToolExecutor


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
        },
        777,
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
    expected_error = ToolArgumentError(tool_name="create_event", original=_sample_validation_error())
    
    tool_executor = SimpleNamespace(
        execute=AsyncMock(side_effect=expected_error)
    )
    agent = AIAgent(deepseek_client=deepseek_client, tool_executor=tool_executor)

    result = await agent.process_message(user_id=42, text="Создай событие")

    assert result == "Исправил формат. Уточните дату в YYYY-MM-DD."
    second_call_messages = deepseek_client.chat_completion.await_args_list[1].kwargs["messages"]
    tool_message = second_call_messages[-1]
    assert tool_message["role"] == "tool"
    assert "Ошибка валидации аргументов" in tool_message["content"]






@pytest.fixture
def ai_agent():
    """
    Фикстура для сборки агента перед каждым тестом.
    Она создает "игрушечные" (mock) версии клиента DeepSeek и ToolExecutor,
    чтобы тест работал быстро и не ходил в интернет.
    """
    # Создаем мок для клиента DeepSeek
    mock_deepseek = AsyncMock(spec=DeepSeekClient)
    
    # Настраиваем мок DeepSeek так, чтобы он имитировал ответ модели, 
    # которая просит вызвать инструмент create_event.
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "create_event"
    mock_tool_call.function.arguments = '{"time": "15:00", "date": "tomorrow"}'
    
    mock_message = MagicMock()
    mock_message.content = ""
    mock_message.tool_calls = [mock_tool_call]
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    
    mock_deepseek.chat_completion.return_value = mock_response

    # Создаем мок для исполнителя инструментов
    mock_executor = AsyncMock(spec=ToolExecutor)

    # Собираем нашего агента, передавая ему фейковые зависимости
    return AIAgent(deepseek_client=mock_deepseek, tool_executor=mock_executor)


@pytest.mark.asyncio
async def test_agent_handles_unexpected_tool_error(ai_agent):
    """
    Тест: Проверяем, что агент корректно обрабатывает непредвиденные ошибки
    (например, таймаут от Google API) при вызове инструментов.
    """
    # Подменяем метод execute у замоканного ToolExecutor так, чтобы он кидал ошибку
    with patch.object(
        ai_agent._tool_executor,
        "execute",
        side_effect=RuntimeError("Google API Timeout"),
    ):
        # Вызываем метод, который хотим протестировать
        response = await ai_agent.process_message(
            user_id=101, 
            text="Запиши на завтра в 15:00 встречу"
        )

        # Проверяем логику ответа
        # Так как после ошибки цикл делает еще одну итерацию к DeepSeek (чтобы отдать tool_result), 
        # и наш мок DeepSeek настроен всегда возвращать tool_call, 
        # цикл дойдет до лимита (_MAX_AGENT_ITERATIONS) и вернет аварийный текст.
        assert "не удалось" in response.lower() or "оно могло быть создано" in response.lower()