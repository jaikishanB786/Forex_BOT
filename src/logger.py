"""
Logging Infrastructure — Centralized, structured logging for the bot.

Uses logzero for coloured console output + optional rotating file logs.

Usage:
    from src.logger import setup_logger
    from src.config import load_config

    cfg = load_config()
    logger = setup_logger(cfg.logging)
    logger.info("Bot started")
    logger.debug("Fetched 200 candles for EURUSD")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import logzero
from logzero import logger as _default_logger

from src.config import LoggingConfig, PROJECT_ROOT


# Map string level names to logging constants
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logger(
    log_cfg: Optional[LoggingConfig] = None,
    name: str = "forex_bot",
) -> logging.Logger:
    """
    Configure and return the application logger.

    Args:
        log_cfg: LoggingConfig dataclass (from config system).
                 If None, uses sensible defaults.
        name: Logger name (used for log file naming).

    Returns:
        A configured logzero Logger instance.
    """
    if log_cfg is None:
        log_cfg = LoggingConfig()

    level = _LEVEL_MAP.get(log_cfg.level.upper(), logging.DEBUG)

    # Console format
    console_format = (
        "%(color)s%(asctime)s | %(levelname)-8s | "
        "%(module)s:%(lineno)d%(end_color)s | %(message)s"
    )
    formatter = logzero.LogFormatter(fmt=console_format, datefmt="%Y-%m-%d %H:%M:%S")
    logzero.setup_default_logger(formatter=formatter, level=level)

    # File logging
    if log_cfg.log_to_file:
        log_dir = PROJECT_ROOT / log_cfg.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}.log"

        file_format = (
            "%(asctime)s | %(levelname)-8s | "
            "%(module)s:%(funcName)s:%(lineno)d | %(message)s"
        )

        logzero.logfile(
            str(log_file),
            maxBytes=5_000_000,      # 5 MB per file
            backupCount=3,           # Keep 3 rotated backups
            loglevel=level,
            formatter=logging.Formatter(fmt=file_format, datefmt="%Y-%m-%d %H:%M:%S"),
        )

    return _default_logger


def get_logger() -> logging.Logger:
    """
    Get the default logzero logger.

    Call setup_logger() first to configure it.
    Falls back to an unconfigured logger if setup hasn't run.
    """
    return _default_logger
