"""Logging setup shared by the Lambda handlers."""

import logging
import os

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def configure_logging() -> None:
    """Apply LOG_LEVEL to the root logger.

    The Lambda Python runtime installs its own handler at WARNING, so without
    this every logger.info call is dropped. An invalid value falls back to INFO
    instead of failing the Lambda at import time.
    """
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(level if level in VALID_LEVELS else "INFO")
