"""Свободный текстовый хендлер для AI-ассистента календаря."""

from aiogram import F, Router
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from app.services.ai.agent import AIAgent


router = Router(name="ai-assistant")


@router.message(F.text, ~F.text.startswith("/"))
async def ai_assistant_handler(
    message: Message,
    ai_agent: AIAgent | None = None,
) -> None:
    if ai_agent is None:
        await message.answer("AI-ассистент не настроен.")
        return

    user = getattr(message, "from_user", None)
    if user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    text = message.text or ""
    if not text.strip():
        await message.answer("Пожалуйста, отправьте текстовый запрос.")
        return

    bot = message.bot
    if bot is None:
        await message.answer("Внутренняя ошибка Telegram-сессии. Попробуйте позже.")
        return

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        response = await ai_agent.process_message(user.id, text)
    await message.answer(response)


def create_router() -> Router:
    return router
