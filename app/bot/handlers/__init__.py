from app.bot.handlers.calendar import create_router as create_calendar_router
from app.bot.handlers.help import create_router as create_help_router
from app.bot.handlers.login import create_router as create_login_router
from app.bot.handlers.ping import create_router as create_ping_router
from app.bot.handlers.start import create_router as create_start_router

__all__ = [
    "create_calendar_router",
    "create_help_router",
    "create_login_router",
    "create_ping_router",
    "create_start_router",
]
