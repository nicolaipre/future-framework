import atexit
import logging
import logging.config
import logging.handlers

from datetime import datetime, timezone
from typing import Any

from uvicorn.logging import AccessFormatter, DefaultFormatter

from future.settings import LOGGING_CONFIG


class UtcTimestampFormatter:
    """Render log timestamps as unambiguous ISO 8601 UTC values."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ANSI color codes
class ColoredFormatter(UtcTimestampFormatter, logging.Formatter):
    """Custom formatter with colors like uvicorn"""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        timestamp = self.formatTime(record)
        levelname = record.levelname
        if levelname in self.COLORS:
            # Calculate padding based on original levelname length BEFORE adding colors
            padding = " " * (9 - len(levelname))  # 9 is max level length (CRITICAL) + 1
            colored_levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
            return f"{timestamp} {colored_levelname}:{padding}{message}"
        return f"{timestamp} {levelname}: {message}"


class UvicornDefaultFormatter(UtcTimestampFormatter, DefaultFormatter):
    """Uvicorn server formatter using Future's UTC timestamp format."""


class UvicornAccessFormatter(UtcTimestampFormatter, AccessFormatter):
    """Uvicorn access formatter using Future's UTC timestamp format."""


def create_uvicorn_logging_config() -> dict[str, Any]:
    """Return a fresh Uvicorn logging config for each server invocation."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": UvicornDefaultFormatter,
                "fmt": "%(asctime)s %(levelprefix)s %(message)s",
                "use_colors": None,
            },
            "access": {
                "()": UvicornAccessFormatter,
                "fmt": '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
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
formatter = ColoredFormatter("%(message)s")

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
