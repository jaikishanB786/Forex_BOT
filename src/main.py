"""
Main — Application entry point for the Forex AI Bot.

This module bootstraps the application:
  1. Loads configuration
  2. Validates settings
  3. Initializes logging
  4. Prints a startup banner

Trading logic is NOT implemented here yet (Phase 2+).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from src.config import load_config, validate_config, BotConfig
from src.logger import setup_logger, get_logger


BANNER = r"""
╔══════════════════════════════════════════════╗
║           FOREX AI BOT  v0.1.0               ║
║         Automated MT5 Trading System         ║
╠══════════════════════════════════════════════╣
║  Mode  : {mode:<37s}║
║  Pairs : {pairs:<37s}║
║  TF    : {tf:<37s}║
║  Risk  : {risk:<37s}║
╚══════════════════════════════════════════════╝
"""


def print_banner(cfg: BotConfig) -> None:
    """Print the startup banner with current config values."""
    pairs = ", ".join(cfg.trading.symbols[:3])
    if len(cfg.trading.symbols) > 3:
        pairs += f" +{len(cfg.trading.symbols) - 3} more"
    risk_pct = f"{cfg.risk.max_risk_per_trade * 100:.1f}% per trade"

    print(
        BANNER.format(
            mode=cfg.trading.mode,
            pairs=pairs,
            tf=cfg.trading.timeframe,
            risk=risk_pct,
        )
    )


def startup() -> BotConfig:
    """
    Run the full startup sequence.

    Returns:
        The loaded and validated BotConfig.

    Raises:
        SystemExit: If critical config validation fails.
    """
    # 1. Load config
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Setup logging (before anything that logs)
    logger = setup_logger(cfg.logging)

    # 3. Print banner
    print_banner(cfg)

    # 4. Validate config
    issues = validate_config(cfg)
    if issues:
        for issue in issues:
            logger.warning(f"Config issue: {issue}")
    else:
        logger.info("Configuration validated — all checks passed")

    # 5. Log startup info
    logger.info(f"Trading mode   : {cfg.trading.mode}")
    logger.info(f"Symbols        : {cfg.trading.symbols}")
    logger.info(f"Timeframe      : {cfg.trading.timeframe}")
    logger.info(f"Strategy       : {cfg.strategy.name}")
    logger.info(f"Max risk/trade : {cfg.risk.max_risk_per_trade * 100:.1f}%")
    logger.info(f"Max daily DD   : {cfg.risk.max_daily_drawdown * 100:.1f}%")
    logger.info(
        f"Started at     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    if cfg.trading.mode == "DRY_RUN":
        logger.info("[DRY_RUN] No real trades will be placed")
    elif cfg.trading.mode == "LIVE":
        logger.warning("[LIVE] Real money trades WILL be placed!")

    return cfg


def main() -> None:
    """Main entry point."""
    cfg = startup()

    logger = get_logger()
    logger.info("Startup complete. Trading engine not yet implemented (Phase 2+).")
    logger.info("Shutting down gracefully.")


if __name__ == "__main__":
    main()
