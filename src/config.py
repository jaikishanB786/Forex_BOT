"""
Configuration System — Loads and validates all bot settings.

Merges settings from:
  1. config/settings.yaml  (defaults & strategy params)
  2. .env file             (secrets & overrides via environment variables)

Usage:
    from src.config import load_config
    cfg = load_config()
    print(cfg.trading.mode)       # "DRY_RUN"
    print(cfg.mt5.login)          # 12345678
    print(cfg.risk.max_risk_per_trade)  # 0.01
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "settings.yaml"
ENV_PATH = PROJECT_ROOT / ".env"
LOGS_DIR = PROJECT_ROOT / "logs"


# ---------------------------------------------------------------------------
# Dataclass hierarchy — typed, immutable-ish config objects
# ---------------------------------------------------------------------------
@dataclass
class MT5Config:
    """MetaTrader 5 connection credentials (from .env)."""
    login: int = 0
    password: str = ""
    server: str = ""
    path: Optional[str] = None


@dataclass
class TradingConfig:
    """General trading parameters."""
    mode: str = "DRY_RUN"
    symbols: List[str] = field(default_factory=lambda: ["EURUSD"])
    symbol_mapping: Dict[str, str] = field(default_factory=dict)
    timeframe: str = "M15"
    candle_count: int = 200
    magic_number: int = 234000
    stale_tick_seconds: int = 300


@dataclass
class StrategyConfig:
    """Strategy selection and parameters."""
    name: str = "moving_average"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskConfig:
    """Risk management parameters."""
    max_risk_per_trade: float = 0.01
    use_fixed_lot: bool = False
    fixed_lot_size: float = 0.01
    max_open_trades: int = 3
    max_daily_drawdown: float = 0.05
    default_sl_pips: int = 30
    default_tp_pips: int = 60
    trailing_stop: bool = False
    trailing_stop_pips: int = 20
    max_spread_points: int = 20
    slippage_points: int = 5


@dataclass
class ScheduleConfig:
    """Scheduling parameters."""
    interval_seconds: int = 60
    trading_hours: Dict[str, str] = field(
        default_factory=lambda: {"start": "01:00", "end": "23:00"}
    )
    skip_weekends: bool = True


@dataclass
class LoggingConfig:
    """Logging parameters."""
    level: str = "DEBUG"
    log_to_file: bool = True
    log_dir: str = "logs"


@dataclass
class NotificationConfig:
    """Notification parameters."""
    enabled: bool = False
    telegram: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


@dataclass
class BotConfig:
    """Root configuration object — aggregates all sections."""
    mt5: MT5Config = field(default_factory=MT5Config)
    trading: TradingConfig = field(default_factory=TradingConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _load_env() -> None:
    """Load .env file into os.environ (does not override existing vars)."""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)


def load_config(config_path: Optional[Path] = None) -> BotConfig:
    """
    Load and merge configuration from YAML + environment variables.

    Priority (highest wins):
        1. Environment variables / .env
        2. config/settings.yaml
        3. Dataclass defaults

    Args:
        config_path: Optional override for the YAML config file path.

    Returns:
        A fully populated BotConfig instance.
    """
    # Load .env first so env vars are available
    _load_env()

    # Load YAML
    yaml_path = config_path or DEFAULT_CONFIG_PATH
    yaml_data = _load_yaml(yaml_path) if yaml_path.exists() else {}

    # ---- MT5 credentials (from environment only — never in YAML) ----
    mt5 = MT5Config(
        login=int(os.getenv("MT5_LOGIN", "0")),
        password=os.getenv("MT5_PASSWORD", ""),
        server=os.getenv("MT5_SERVER", ""),
        path=os.getenv("MT5_PATH"),
    )

    # ---- Trading ----
    trading_data = yaml_data.get("trading", {})
    # .env TRADING_MODE overrides YAML
    mode = os.getenv("TRADING_MODE", trading_data.get("mode", "DRY_RUN"))
    trading = TradingConfig(
        mode=mode.upper(),
        symbols=trading_data.get("symbols", ["EURUSD"]),
        symbol_mapping=trading_data.get("symbol_mapping") or {},
        timeframe=trading_data.get("timeframe", "M15"),
        candle_count=trading_data.get("candle_count", 200),
        magic_number=trading_data.get("magic_number", 234000),
        stale_tick_seconds=trading_data.get("stale_tick_seconds", 300),
    )

    # ---- Strategy ----
    strat_data = yaml_data.get("strategy", {})
    strategy = StrategyConfig(
        name=strat_data.get("name", "moving_average"),
        params=strat_data.get("params", {}),
    )

    # ---- Risk ----
    risk_data = yaml_data.get("risk", {})
    risk = RiskConfig(
        max_risk_per_trade=risk_data.get("max_risk_per_trade", 0.01),
        use_fixed_lot=risk_data.get("use_fixed_lot", False),
        fixed_lot_size=risk_data.get("fixed_lot_size", 0.01),
        max_open_trades=risk_data.get("max_open_trades", 3),
        max_daily_drawdown=risk_data.get("max_daily_drawdown", 0.05),
        default_sl_pips=risk_data.get("default_sl_pips", 30),
        default_tp_pips=risk_data.get("default_tp_pips", 60),
        trailing_stop=risk_data.get("trailing_stop", False),
        trailing_stop_pips=risk_data.get("trailing_stop_pips", 20),
        max_spread_points=risk_data.get("max_spread_points", 20),
        slippage_points=risk_data.get("slippage_points", 5),
    )

    # ---- Schedule ----
    sched_data = yaml_data.get("schedule", {})
    schedule = ScheduleConfig(
        interval_seconds=sched_data.get("interval_seconds", 60),
        trading_hours=sched_data.get(
            "trading_hours", {"start": "01:00", "end": "23:00"}
        ),
        skip_weekends=sched_data.get("skip_weekends", True),
    )

    # ---- Logging ----
    log_data = yaml_data.get("logging", {})
    logging_cfg = LoggingConfig(
        level=log_data.get("level", "DEBUG"),
        log_to_file=log_data.get("log_to_file", True),
        log_dir=log_data.get("log_dir", "logs"),
    )

    # ---- Notifications ----
    notif_data = yaml_data.get("notifications", {})
    notifications = NotificationConfig(
        enabled=notif_data.get("enabled", False),
        telegram=notif_data.get("telegram", False),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
    )

    return BotConfig(
        mt5=mt5,
        trading=trading,
        strategy=strategy,
        risk=risk,
        schedule=schedule,
        logging=logging_cfg,
        notifications=notifications,
    )


def validate_config(cfg: BotConfig) -> List[str]:
    """
    Validate a BotConfig and return a list of warnings/errors.

    Returns an empty list if everything is valid.
    """
    issues: List[str] = []

    # MT5 credentials
    if cfg.mt5.login == 0:
        issues.append("MT5_LOGIN is not set (check .env file)")
    if not cfg.mt5.password:
        issues.append("MT5_PASSWORD is not set (check .env file)")
    if not cfg.mt5.server:
        issues.append("MT5_SERVER is not set (check .env file)")

    # Trading mode
    if cfg.trading.mode not in ("DRY_RUN", "LIVE"):
        issues.append(
            f"Invalid TRADING_MODE '{cfg.trading.mode}' — must be DRY_RUN or LIVE"
        )

    # Risk sanity
    if not 0 < cfg.risk.max_risk_per_trade <= 0.10:
        issues.append(
            f"max_risk_per_trade={cfg.risk.max_risk_per_trade} is outside safe "
            f"range (0, 0.10]. Using >10% risk per trade is extremely dangerous."
        )

    if not 0 < cfg.risk.max_daily_drawdown <= 0.20:
        issues.append(
            f"max_daily_drawdown={cfg.risk.max_daily_drawdown} is outside safe "
            f"range (0, 0.20]."
        )

    # Symbols
    if not cfg.trading.symbols:
        issues.append("No trading symbols configured")

    return issues
