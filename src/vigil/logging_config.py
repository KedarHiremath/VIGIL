"""Centralised logging configuration for VIGIL.

Call ``configure_logging()`` once at application start-up (done automatically
from ``vigil/api/app.py``) to install a consistent, timestamped log format
across every module and the uvicorn access/error loggers.
"""

from __future__ import annotations

import logging
import logging.config
from typing import Any


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_log_config(log_level: str = "INFO") -> dict[str, Any]:
    """Return a ``logging.config.dictConfig``-compatible configuration dict.

    The format includes:
      * ISO-8601 timestamp (local time with timezone offset)
      * Log level (right-padded to 8 chars)
      * Logger name
      * Message

    Example output::

        2026-10-21 15:04:23 +0530 | INFO     | vigil.models.gemini | GeminiClient: attempt 1/3 …
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S %z"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "timestamped": {
                "format": fmt,
                "datefmt": datefmt,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "timestamped",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level.upper(),
        },
        # Ensure uvicorn's own loggers also use our formatter.
        "loggers": {
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
                # Access log records carry the request line; keep them.
            },
            "fastapi": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "vigil": {
                "handlers": ["console"],
                "level": log_level.upper(),
                "propagate": False,
            },
        },
    }


def configure_logging(log_level: str | None = None) -> None:
    """Install VIGIL's timestamped logging configuration.

    Safe to call multiple times – subsequent calls are no-ops unless the
    level is explicitly changed.
    """
    from vigil.config import config  # local import avoids circular deps at module load

    level = log_level or config.log_level
    logging.config.dictConfig(get_log_config(level))
