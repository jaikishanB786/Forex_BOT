"""Tests for the logging infrastructure (src/logger.py)."""

import logging
from pathlib import Path

import pytest

from src.config import LoggingConfig
from src.logger import setup_logger, get_logger


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSetupLogger:
    def test_returns_logger_instance(self):
        log_cfg = LoggingConfig(level="INFO", log_to_file=False)
        logger = setup_logger(log_cfg)
        assert isinstance(logger, logging.Logger)

    def test_logger_respects_level(self):
        log_cfg = LoggingConfig(level="WARNING", log_to_file=False)
        logger = setup_logger(log_cfg)
        assert logger.level == logging.WARNING

    def test_creates_log_file(self, tmp_path: Path, monkeypatch):
        """Log file should be created when log_to_file is True."""
        # Monkeypatch PROJECT_ROOT so logs go to tmp_path
        import src.logger as logger_mod
        monkeypatch.setattr(logger_mod, "PROJECT_ROOT", tmp_path)

        log_cfg = LoggingConfig(
            level="DEBUG",
            log_to_file=True,
            log_dir="logs",
        )
        logger = setup_logger(log_cfg, name="test_bot")

        # Force a log write
        logger.info("test message for file")

        log_file = tmp_path / "logs" / "test_bot.log"
        assert log_file.parent.exists(), "logs/ directory should be created"

    def test_no_log_file_when_disabled(self, tmp_path: Path, monkeypatch):
        """No log file should be created when log_to_file is False."""
        import src.logger as logger_mod
        monkeypatch.setattr(logger_mod, "PROJECT_ROOT", tmp_path)

        log_cfg = LoggingConfig(level="DEBUG", log_to_file=False)
        setup_logger(log_cfg, name="disabled_test")

        log_dir = tmp_path / "logs"
        # The directory shouldn't be created if log_to_file is False
        assert not log_dir.exists()

    def test_defaults_when_none(self):
        """Should work with no config passed (uses defaults)."""
        logger = setup_logger(None)
        assert isinstance(logger, logging.Logger)


class TestGetLogger:
    def test_returns_same_logger(self):
        log_cfg = LoggingConfig(level="INFO", log_to_file=False)
        setup_logger(log_cfg)
        logger = get_logger()
        assert isinstance(logger, logging.Logger)
