from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message

from app.services.user import UserService


async def handle_start(message: Message, command: CommandObject, user_service: UserService) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить пользователя. Попробуйте ещё раз.")
        return

    await user_service.register_or_update(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
        language_code=telegram_user.language_code,
    )
    if command.args == "auth_success":
        await message.answer(
            "✅ <b>Авторизация успешно завершена!</b>\n\n"
            "Токены сохранены. Теперь я могу управлять вашим Google Календарем. "
            "Напишите мне, что нужно запланировать!",
            parse_mode="HTML"
        )
    else:
        # 3. Стандартное приветствие, если аргументов нет
        await message.answer(
            "Ядро календарного помощника запущено и готово к работе."
        )


def create_router() -> Router:
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    return router
