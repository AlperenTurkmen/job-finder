"""Project-wide logging configuration helpers."""
from __future__ import annotations

import logging
import os
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level_name: Optional[str] = None) -> None:
    """Configure the root logger if it has not been configured yet.

    Parameters
    ----------
    level_name:
        Optional logging level name. If omitted, ``LOG_LEVEL`` from the
        environment (default ``INFO``) is used.
    """
    resolved_level = (level_name or os.getenv("LOG_LEVEL", "INFO")).upper()
    numeric_level = getattr(logging, resolved_level, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=numeric_level,
            format=_DEFAULT_FORMAT,
            datefmt=_DEFAULT_DATE_FORMAT,
        )
    else:
        root_logger.setLevel(numeric_level)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger configured with project defaults."""
    configure_logging()
    return logging.getLogger(name)
