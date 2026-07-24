"""Маршрут callback для Google OAuth."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.dependencies import get_google_auth_service
from app.services.google_auth import GoogleAuthService

router = APIRouter()

import logging
logger = logging.getLogger(__name__)


@router.get("/auth/google/callback")
async def google_oauth_callback(
    request: Request,
    auth_service: GoogleAuthService = Depends(get_google_auth_service),
):
    """Принимает ответ от Google, сохраняет токены в БД и возвращает в бота."""
    
    code = request.query_params.get("code")
    state = request.query_params.get("state") # Здесь лежит telegram_id!

    if not code or not state:
        return JSONResponse(
            status_code=400, 
            content={"detail": "Missing Google OAuth code or state (telegram_id)"}
        )

    try:
        # 1. Проверяем безопасность: расшифровываем state и достаем telegram_id.
        # Если токен подделан или протух, эта функция выкинет ValueError
        telegram_id = auth_service.verify_state_token(state)

        # 2. Отдаем код, проверенный telegram_id и оригинальный state в сервис для обмена на токены
        await auth_service.exchange_code_for_tokens(
            code=code, 
            telegram_id=telegram_id, 
            state=state
        )

        # 3. Перекидываем пользователя обратно в Telegram
        # Лайфхак: добавили deep link параметр start=auth_success
        bot_url = "https://t.me/ai_assistent9_bot?start=auth_success"
        return RedirectResponse(url=bot_url)

    except ValueError as e:
        # Сюда мы попадем, если JWT протух или был подделан
        logger.warning(f"OAuth validation failed: {str(e)}")
        return JSONResponse(status_code=400, content={"detail": str(e)})
    except Exception:
        logger.exception("Google OAuth callback failed")
        return JSONResponse(
            status_code=500,
            content={"detail": "Authentication failed"},
        )