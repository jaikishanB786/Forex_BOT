"""Tests for the configuration system (src/config.py)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.config import (
    BotConfig,
    MT5Config,
    TradingConfig,
    RiskConfig,
    load_config,
    validate_config,
    _load_yaml,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_yaml(tmp_path: Path) -> Path:
    """Create a minimal settings.yaml in a temp directory."""
    config = {
        "trading": {
            "mode": "DRY_RUN",
            "symbols": ["EURUSD", "GBPUSD"],
            "timeframe": "H1",
            "candle_count": 100,
            "magic_number": 999000,
        },
        "strategy": {
            "name": "moving_average",
            "params": {"fast_period": 5, "slow_period": 20},
        },
        "risk": {
            "max_risk_per_trade": 0.02,
            "max_open_trades": 2,
            "max_daily_drawdown": 0.03,
            "default_sl_pips": 25,
            "default_tp_pips": 50,
        },
        "schedule": {
            "interval_seconds": 30,
        },
        "logging": {
            "level": "INFO",
            "log_to_file": False,
        },
        "notifications": {
            "enabled": False,
        },
    }
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text(yaml.dump(config), encoding="utf-8")
    return yaml_path


@pytest.fixture
def env_vars():
    """Provide MT5 environment variables for testing."""
    return {
        "MT5_LOGIN": "12345678",
        "MT5_PASSWORD": "test_pass",
        "MT5_SERVER": "TestBroker-Demo",
        "TRADING_MODE": "DRY_RUN",
    }


# ---------------------------------------------------------------------------
# Tests: YAML loading
# ---------------------------------------------------------------------------
class TestLoadYaml:
    def test_loads_valid_yaml(self, sample_yaml: Path):
        data = _load_yaml(sample_yaml)
        assert isinstance(data, dict)
        assert "trading" in data
        assert data["trading"]["timeframe"] == "H1"

    def test_raises_on_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            _load_yaml(tmp_path / "nonexistent.yaml")

    def test_returns_empty_dict_for_empty_yaml(self, tmp_path: Path):
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("", encoding="utf-8")
        result = _load_yaml(empty_file)
        assert result == {}


# ---------------------------------------------------------------------------
# Tests: Config loading
# ---------------------------------------------------------------------------
class TestLoadConfig:
    def test_loads_from_yaml_and_env(self, sample_yaml: Path, env_vars: dict):
        with patch.dict(os.environ, env_vars, clear=False):
            cfg = load_config(config_path=sample_yaml)

        # MT5 from env
        assert cfg.mt5.login == 12345678
        assert cfg.mt5.password == "test_pass"
        assert cfg.mt5.server == "TestBroker-Demo"

        # Trading from YAML
        assert cfg.trading.symbols == ["EURUSD", "GBPUSD"]
        assert cfg.trading.timeframe == "H1"
        assert cfg.trading.candle_count == 100
        assert cfg.trading.mode == "DRY_RUN"

        # Risk from YAML
        assert cfg.risk.max_risk_per_trade == 0.02
        assert cfg.risk.max_open_trades == 2

    def test_env_trading_mode_overrides_yaml(self, sample_yaml: Path, env_vars: dict):
        """TRADING_MODE in env should override the YAML value."""
        env_override = {**env_vars, "TRADING_MODE": "DRY_RUN"}
        with patch.dict(os.environ, env_override, clear=False):
            cfg = load_config(config_path=sample_yaml)
        assert cfg.trading.mode == "DRY_RUN"

    def test_defaults_when_no_yaml(self, tmp_path: Path, env_vars: dict):
        """Should use dataclass defaults when YAML has no matching section."""
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text("---\n", encoding="utf-8")
        with patch.dict(os.environ, env_vars, clear=False):
            cfg = load_config(config_path=minimal)
        assert cfg.trading.mode == "DRY_RUN"
        assert cfg.trading.symbols == ["EURUSD"]
        assert cfg.risk.max_risk_per_trade == 0.01

    def test_returns_botconfig_type(self, sample_yaml: Path, env_vars: dict):
        with patch.dict(os.environ, env_vars, clear=False):
            cfg = load_config(config_path=sample_yaml)
        assert isinstance(cfg, BotConfig)


# ---------------------------------------------------------------------------
# Tests: Config validation
# ---------------------------------------------------------------------------
class TestValidateConfig:
    def test_valid_config_has_no_issues(self):
        cfg = BotConfig(
            mt5=MT5Config(login=123, password="pw", server="srv"),
            trading=TradingConfig(mode="DRY_RUN"),
            risk=RiskConfig(max_risk_per_trade=0.01, max_daily_drawdown=0.05),
        )
        issues = validate_config(cfg)
        assert issues == []

    def test_catches_missing_mt5_credentials(self):
        cfg = BotConfig()  # All defaults — MT5 creds are empty
        issues = validate_config(cfg)
        assert any("MT5_LOGIN" in i for i in issues)
        assert any("MT5_PASSWORD" in i for i in issues)
        assert any("MT5_SERVER" in i for i in issues)

    def test_catches_invalid_trading_mode(self):
        cfg = BotConfig(
            mt5=MT5Config(login=1, password="p", server="s"),
            trading=TradingConfig(mode="INVALID"),
        )
        issues = validate_config(cfg)
        assert any("TRADING_MODE" in i for i in issues)

    def test_catches_excessive_risk(self):
        cfg = BotConfig(
            mt5=MT5Config(login=1, password="p", server="s"),
            risk=RiskConfig(max_risk_per_trade=0.50),  # 50% — way too high
        )
        issues = validate_config(cfg)
        assert any("max_risk_per_trade" in i for i in issues)

    def test_catches_excessive_drawdown(self):
        cfg = BotConfig(
            mt5=MT5Config(login=1, password="p", server="s"),
            risk=RiskConfig(max_daily_drawdown=0.90),  # 90%
        )
        issues = validate_config(cfg)
        assert any("max_daily_drawdown" in i for i in issues)

    def test_catches_empty_symbols(self):
        cfg = BotConfig(
            mt5=MT5Config(login=1, password="p", server="s"),
            trading=TradingConfig(symbols=[]),
        )
        issues = validate_config(cfg)
        assert any("symbols" in i for i in issues)
