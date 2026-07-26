"""Изолирует сбор тестов от содержимого пользовательского .env."""

import os

from tests.constants import DUMMY_BOT_TOKEN


TEST_ENVIRONMENT = {
    "BOT_TOKEN": DUMMY_BOT_TOKEN,
    "DEBUG": "false",
    "HOST": "127.0.0.1",
    "PORT": "8000",
    "BOT_MODE": "polling",
    "WEBHOOK_BASE_URL": "",
    "WEBHOOK_PATH": "/telegram/webhook",
    "WEBHOOK_SECRET": "",
    "GOOGLE_CALENDAR_ENABLED": "false",
    "GOOGLE_CALENDAR_TIMEZONE": "Europe/Moscow",
    "GOOGLE_CALENDAR_MAX_RESULTS": "10",
    "TESTING": "true",
}

for name, value in TEST_ENVIRONMENT.items():
    os.environ[name] = value
