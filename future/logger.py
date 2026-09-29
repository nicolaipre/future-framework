import atexit
import http
import logging
import logging.config
import logging.handlers

from datetime import datetime, timezone
from typing import Any

from uvicorn.logging import AccessFormatter, DefaultFormatter

from future.settings import LOGGING_CONFIG


RESET = "\033[0m"
LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",       # Cyan
    logging.INFO: "\033[32m",        # Green
    logging.WARNING: "\033[38;5;208m",  # Orange
    logging.ERROR: "\033[31m",       # Red
    logging.CRITICAL: "\033[91m",    # Bright red
}
HTTP_STATUS_COLORS = {
    1: "\033[96m",  # Bright cyan
    2: "\033[97m",  # Bright white
    3: "\033[92m",  # Bright green
    4: "\033[91m",  # Bright red
    5: "\033[94m",  # Bright blue
}
DEFAULT_LOG_FORMAT = "%(asctime)s %(levelprefix)s %(message)s"
ACCESS_LOG_FORMAT = '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'


def _colorize(value: str, color: str | None) -> str:
    return f"{color}{value}{RESET}" if color else value


class UtcTimestampFormatter:
    """Render log timestamps as unambiguous ISO 8601 UTC values."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def color_level_name(self, level_name: str, level_no: int) -> str:
        return _colorize(level_name, LEVEL_COLORS.get(level_no))


class ColoredFormatter(UtcTimestampFormatter, DefaultFormatter):
    """Shared timestamp and level formatter for Future and Uvicorn."""


class UvicornDefaultFormatter(UtcTimestampFormatter, DefaultFormatter):
    """Uvicorn server formatter using Future's UTC timestamp format."""


class UvicornAccessFormatter(UtcTimestampFormatter, AccessFormatter):
    """Uvicorn access formatter using Future's UTC timestamp format."""

    def get_status_code(self, status_code: int) -> str:
        try:
            status_phrase = http.HTTPStatus(status_code).phrase
        except ValueError:
            status_phrase = ""
        status_and_phrase = f"{status_code} {status_phrase}"
        if not self.use_colors:
            return status_and_phrase
        return _colorize(status_and_phrase, HTTP_STATUS_COLORS.get(status_code // 100))


def create_uvicorn_logging_config() -> dict[str, Any]:
    """Return a fresh Uvicorn logging config for each server invocation."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": UvicornDefaultFormatter,
                "fmt": DEFAULT_LOG_FORMAT,
                "use_colors": True,
            },
            "access": {
                "()": UvicornAccessFormatter,
                "fmt": ACCESS_LOG_FORMAT,
                "use_colors": True,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


# Configure logging using settings
logging.config.dictConfig(LOGGING_CONFIG)

log = logging.getLogger("future")
formatter = ColoredFormatter(DEFAULT_LOG_FORMAT, use_colors=True)

# QueueHandler itself does not format; the listener's stdout handler does.
# Handler level NOTSET so Future's log.setLevel(APP_DEBUG) alone controls filtering.
queue_handler = logging.getHandlerByName("queue_handler")
if queue_handler is not None and isinstance(queue_handler, logging.handlers.QueueHandler):
    listener = getattr(queue_handler, "listener", None)
    if listener is not None:
        for handler in listener.handlers:
            handler.setFormatter(formatter)
            handler.setLevel(logging.NOTSET)
        listener.start()
        atexit.register(listener.stop)
else:
    for handler in log.handlers:
        handler.setFormatter(formatter)
        handler.setLevel(logging.NOTSET)
