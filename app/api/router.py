"""Собирает маршруты FastAPI."""

from fastapi import APIRouter

from app.api.google_auth import router as google_auth_router
from app.api.health import router as health_router
from app.api.webhook import create_webhook_router
from app.config import Settings


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(google_auth_router)
    router.include_router(create_webhook_router(settings.WEBHOOK_PATH))
    return router
