"""Безопасный разбор IANA-имени часового пояса."""

import logging
from datetime import tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def parse_time_zone(value: str | None, default: tzinfo) -> tzinfo:
    if not value:
        return default
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Invalid IANA time zone '%s'; falling back to default", value)
        return default