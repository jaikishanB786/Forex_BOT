"""Tests for the main entry point (src/main.py)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.main import startup, print_banner
from src.config import BotConfig, MT5Config, TradingConfig, RiskConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def valid_yaml(tmp_path: Path) -> Path:
    """Create a valid settings.yaml for startup tests."""
    config = {
        "trading": {
            "mode": "DRY_RUN",
            "symbols": ["EURUSD"],
            "timeframe": "M15",
        },
        "logging": {
            "level": "WARNING",
            "log_to_file": False,
        },
    }
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text(yaml.dump(config), encoding="utf-8")
    return yaml_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestPrintBanner:
    def test_banner_does_not_crash(self, capsys):
        cfg = BotConfig(
            trading=TradingConfig(mode="DRY_RUN", symbols=["EURUSD", "GBPUSD"]),
            risk=RiskConfig(max_risk_per_trade=0.02),
        )
        print_banner(cfg)
        captured = capsys.readouterr()
        assert "FOREX AI BOT" in captured.out
        assert "DRY_RUN" in captured.out
        assert "EURUSD" in captured.out

    def test_banner_truncates_many_symbols(self, capsys):
        cfg = BotConfig(
            trading=TradingConfig(
                symbols=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD"]
            ),
        )
        print_banner(cfg)
        captured = capsys.readouterr()
        assert "+2 more" in captured.out


class TestStartup:
    def test_startup_returns_config(self, valid_yaml: Path):
        env = {
            "MT5_LOGIN": "99999",
            "MT5_PASSWORD": "pw",
            "MT5_SERVER": "Test-Server",
            "TRADING_MODE": "DRY_RUN",
        }
        with patch("src.config.DEFAULT_CONFIG_PATH", valid_yaml), \
             patch("src.config.ENV_PATH", valid_yaml.parent / ".env"), \
             patch.dict(os.environ, env, clear=False):
            cfg = startup()
        assert isinstance(cfg, BotConfig)
        assert cfg.trading.mode == "DRY_RUN"
