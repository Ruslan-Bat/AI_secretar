"""Низкоуровневый клиент DeepSeek API."""

from typing import Any, cast

from openai import AsyncOpenAI

_DEFAULT_TIMEOUT_SECONDS: float = 30.0

class DeepSeekClient:
    """Обертка над AsyncOpenAI для запросов к DeepSeek."""

    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=timeout,
        )

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        # OpenAI/AsyncOpenAI type hints expect specialized message/tool param types.
        # Cast to Any to satisfy runtime usage and silence static type checkers.
        return await self._client.chat.completions.create(
            model="deepseek-chat",
            messages=cast(Any, messages),  # type: ignore[arg-type]
            tools=cast(Any, tools),        # type: ignore[arg-type]
        )
