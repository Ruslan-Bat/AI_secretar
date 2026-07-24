"""Собирает FastAPI, управляет жизненным циклом Telegram и предоставляет точку входа."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import create_api_router
from app.bot.lifecycle import BotRuntime, start_bot_runtime, stop_bot_runtime
from app.config import Settings, load_settings
from app.core.logging import configure_logging
from app.dependencies import AppContainer, build_container


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    container: AppContainer | None = None,
) -> FastAPI:
    resolved_settings = settings if settings is not None else load_settings()
    resolved_container = (
        container if container is not None else build_container(resolved_settings)
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_logging(debug=resolved_settings.DEBUG)
        logger.info("Starting application")
        logger.info("Bot mode: %s", resolved_settings.BOT_MODE)

        runtime: BotRuntime | None = None
        application.state.bot_runtime = None
        if not resolved_settings.TESTING:
            runtime = await start_bot_runtime(resolved_settings, resolved_container)
            application.state.bot_runtime = runtime

        try:
            yield
        finally:
            if runtime is not None:
                await stop_bot_runtime(runtime)
            logger.info("Application stopped")

    application = FastAPI(
        title="Telegram Calendar Bot",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.container = resolved_container
    application.state.bot_runtime = None
    application.include_router(create_api_router(resolved_settings))

    @application.exception_handler(Exception)
    async def handle_unexpected_http_error(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled HTTP error on %s (%s)",
            request.url.path,
            type(error).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return application


app = create_app()


def run() -> None:
    settings: Settings = app.state.settings
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="debug" if settings.DEBUG else "info",
    )


if __name__ == "__main__":
    run()
