"""Centralised logging configuration for VIGIL with ANSI colour coding.

Installs a consistent, timestamped, colour-coded log format across every module,
FastAPI access middleware, and uvicorn access/error loggers. HTTP response codes
are augmented with contextual status phrases (e.g., 200 OK, 404 NOT FOUND) and
color-coded by outcome severity.
"""

from __future__ import annotations

import http
import logging
import logging.config
import os
import re
import sys
from typing import Any

# Enable ANSI escape sequences on Windows console
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11
        h_stdout = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(h_stdout, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(h_stdout, mode.value | 0x0004)
        # STD_ERROR_HANDLE = -12
        h_stderr = kernel32.GetStdHandle(-12)
        if kernel32.GetConsoleMode(h_stderr, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h_stderr, mode.value | 0x0004)
    except Exception:
        # Fallback to empty command enabling ANSI
        try:
            os.system("")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ANSI Colour Palette
# ---------------------------------------------------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

COLOR_DEBUG = "\033[36m"         # Cyan
COLOR_INFO = "\033[32m"          # Green
COLOR_WARNING = "\033[33m"       # Yellow
COLOR_ERROR = "\033[31m"         # Red
COLOR_CRITICAL = "\033[97;41m"   # Bold white on red

COLOR_HTTP_2XX = "\033[1;92m"    # Bold Bright Green
COLOR_HTTP_3XX = "\033[1;96m"    # Bold Bright Cyan
COLOR_HTTP_4XX = "\033[1;93m"    # Bold Bright Yellow
COLOR_HTTP_5XX = "\033[1;91m"    # Bold Bright Red

LEVEL_COLORS = {
    logging.DEBUG: COLOR_DEBUG,
    logging.INFO: COLOR_INFO,
    logging.WARNING: COLOR_WARNING,
    logging.ERROR: COLOR_ERROR,
    logging.CRITICAL: COLOR_CRITICAL,
}

# Pre-compile regex for HTTP status codes in messages
# Matches patterns like ' 200 ', ' 200 OK', ' 404 NOT FOUND', ' 404 Not Found', '" 200 '
HTTP_STATUS_PATTERN = re.compile(
    r'(?P<prefix>[\s"\'])'
    r'(?P<code>[1-5]\d{2})'
    r'(?:\s+(?P<phrase>[A-Za-z_\s\-]+?))?'
    r'(?P<suffix>[\s"\'\(\)\,\.\|]|$)',
)


def _get_status_phrase(code: int) -> str:
    """Retrieve standard uppercase HTTP reason phrase for status code."""
    try:
        return http.HTTPStatus(code).phrase.upper()
    except ValueError:
        return "RESPONSE"


def _colorize_http_status_match(match: re.Match[str]) -> str:
    """Colorize an HTTP status code and ensure its contextual phrase is present."""
    prefix = match.group("prefix")
    code_str = match.group("code")
    raw_phrase = match.group("phrase")
    suffix = match.group("suffix")

    try:
        code_int = int(code_str)
    except ValueError:
        return match.group(0)

    # Determine standard phrase
    phrase = raw_phrase.strip().upper() if raw_phrase and len(raw_phrase.strip()) > 1 else _get_status_phrase(code_int)

    # Pick colour by status class
    if 200 <= code_int < 300:
        color = COLOR_HTTP_2XX
    elif 300 <= code_int < 400:
        color = COLOR_HTTP_3XX
    elif 400 <= code_int < 500:
        color = COLOR_HTTP_4XX
    elif 500 <= code_int < 600:
        color = COLOR_HTTP_5XX
    else:
        color = BOLD

    return f"{prefix}{color}{code_int} {phrase}{RESET}{suffix}"


class VigilColorizedFormatter(logging.Formatter):
    """Custom formatter preserving existing format with ANSI colour enhancements.

    Standard format:
      %(asctime)s | %(levelname)-8s | %(name)s | %(message)s

    Features:
      - Colorized log levels (INFO, WARNING, ERROR, etc.)
      - Colorized HTTP status codes with output code context (e.g., 200 OK, 404 NOT FOUND)
      - Preserves clean alignment and exact field ordering
    """

    def format(self, record: logging.LogRecord) -> str:
        # Create a copy or handle record message
        orig_msg = record.getMessage()

        # Format asctime
        asctime = self.formatTime(record, self.datefmt)

        # Colorize levelname
        level_color = LEVEL_COLORS.get(record.levelno, "")
        raw_level = f"{record.levelname:<8}"
        if level_color:
            colored_level = f"{level_color}{raw_level}{RESET}"
        else:
            colored_level = raw_level

        # Augment HTTP status codes with context phrase and color in access logs / messages
        colored_msg = HTTP_STATUS_PATTERN.sub(_colorize_http_status_match, orig_msg)

        # Assemble format: %(asctime)s | %(levelname)-8s | %(name)s | %(message)s
        formatted = f"{asctime} | {colored_level} | {record.name} | {colored_msg}"

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            formatted = f"{formatted}\n{record.exc_text}"
        if record.stack_info:
            formatted = f"{formatted}\n{self.formatStack(record.stack_info)}"

        return formatted


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_log_config(log_level: str = "INFO") -> dict[str, Any]:
    """Return a ``logging.config.dictConfig``-compatible configuration dict.

    The format preserves:
      * ISO-8601 timestamp (local time with timezone offset)
      * Log level (right-padded to 8 chars, colour coded)
      * Logger name
      * Message (with colour coded HTTP status output code context)
    """
    datefmt = "%Y-%m-%d %H:%M:%S %z"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "timestamped": {
                "()": VigilColorizedFormatter,
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
            "vigil.access": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }


def configure_logging(log_level: str | None = None) -> None:
    """Install VIGIL's timestamped colour-coded logging configuration.

    Safe to call multiple times – subsequent calls are no-ops unless the
    level is explicitly changed.
    """
    from vigil.config import config  # local import avoids circular deps at module load

    level = log_level or config.log_level
    logging.config.dictConfig(get_log_config(level))
