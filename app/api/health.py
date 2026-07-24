from fastapi import APIRouter, Request

from app.config import Settings

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    return {
        "status": "ok",
        "service": "telegram-calendar-bot",
        "bot_mode": settings.BOT_MODE,
    }
