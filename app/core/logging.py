"""Централизованная настройка логирования."""

import logging
import sys


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def configure_logging(*, debug: bool = False) -> None:
    """Настраивает вывод логов приложения."""

    file_handler = logging.FileHandler("app.log", encoding="utf-8", mode="a")
    console_handler = logging.StreamHandler(sys.stdout)
    
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,

        handlers=[file_handler], # можно добавить console_handler, если нужно выводить в консоль

        force=True,
    )
    logging.captureWarnings(True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
