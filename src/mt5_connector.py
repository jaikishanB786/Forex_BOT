"""
MT5 Connector — Manages the MetaTrader 5 terminal connection lifecycle.

Responsibilities:
  - Initialize and log in to the MT5 terminal
  - Retrieve terminal and account information
  - Validate account type (HEDGING required)
  - Connection health checks
  - Graceful shutdown

Usage:
    from src.mt5_connector import MT5Connector
    from src.config import load_config

    cfg = load_config()
    connector = MT5Connector(cfg)
    connector.connect()
    info = connector.get_account_summary()
    connector.disconnect()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import MetaTrader5 as mt5

from src.config import BotConfig
from src.logger import get_logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MARGIN_MODE_NAMES = {
    mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING: "NETTING",
    mt5.ACCOUNT_MARGIN_MODE_EXCHANGE: "EXCHANGE",
    mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING: "HEDGING",
}

TRADE_MODE_NAMES = {
    mt5.ACCOUNT_TRADE_MODE_DEMO: "DEMO",
    mt5.ACCOUNT_TRADE_MODE_CONTEST: "CONTEST",
    mt5.ACCOUNT_TRADE_MODE_REAL: "REAL",
}


# ---------------------------------------------------------------------------
# Data classes for structured output
# ---------------------------------------------------------------------------
@dataclass
class TerminalInfo:
    """Parsed MT5 terminal information."""
    connected: bool = False
    build: int = 0
    name: str = ""
    path: str = ""
    data_path: str = ""
    company: str = ""
    trade_allowed: bool = False
    community_account: bool = False
    community_connection: bool = False
    raw: Optional[Any] = field(default=None, repr=False)


@dataclass
class AccountSummary:
    """Parsed MT5 account information."""
    login: int = 0
    name: str = ""
    server: str = ""
    company: str = ""          # Broker name
    currency: str = ""
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    margin_free: float = 0.0
    margin_level: float = 0.0
    leverage: int = 0
    trade_mode: str = ""       # DEMO / REAL / CONTEST
    trade_allowed: bool = False
    trade_expert: bool = False  # Expert Advisors allowed
    margin_mode: str = ""      # HEDGING / NETTING / EXCHANGE
    margin_mode_id: int = -1
    is_hedging: bool = False
    limit_orders: int = 0
    raw: Optional[Any] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class MT5ConnectionError(Exception):
    """Raised when MT5 terminal connection fails."""
    pass


class MT5LoginError(Exception):
    """Raised when MT5 login fails."""
    pass


class AccountTypeError(Exception):
    """Raised when account is not HEDGING (required for this bot)."""
    pass


# ---------------------------------------------------------------------------
# Connector class
# ---------------------------------------------------------------------------
class MT5Connector:
    """
    Manages the full lifecycle of a MetaTrader 5 connection.

    Attributes:
        cfg: The bot configuration.
        logger: Logger instance.
        is_connected: Whether the terminal is connected.
        terminal: Parsed terminal info (populated after connect).
        account: Parsed account summary (populated after connect).
    """

    def __init__(self, cfg: BotConfig, logger: Optional[logging.Logger] = None):
        self.cfg = cfg
        self.logger = logger or get_logger()
        self.is_connected: bool = False
        self.terminal: Optional[TerminalInfo] = None
        self.account: Optional[AccountSummary] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> AccountSummary:
        """
        Initialize MT5, log in, fetch terminal/account info, and validate.

        Returns:
            AccountSummary with full account details.

        Raises:
            MT5ConnectionError: If mt5.initialize() fails.
            MT5LoginError: If mt5.login() fails.
            AccountTypeError: If account is NETTING and mode is LIVE.
        """
        self._initialize()
        self._login()
        self.terminal = self._fetch_terminal_info()
        self.account = self._fetch_account_info()
        self._validate_account()
        self.is_connected = True
        self.logger.info("MT5 connection established successfully")
        return self.account

    def disconnect(self) -> None:
        """Gracefully shut down the MT5 connection."""
        if self.is_connected:
            mt5.shutdown()
            self.is_connected = False
            self.logger.info("MT5 connection closed")

    def __enter__(self) -> "MT5Connector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a live health check on the MT5 connection.

        Returns:
            Dict with connection status, terminal info, and account balance.
        """
        result: Dict[str, Any] = {
            "connected": False,
            "terminal_connected": False,
            "trade_allowed": False,
            "account_login": 0,
            "balance": 0.0,
            "equity": 0.0,
        }

        try:
            t_info = mt5.terminal_info()
            if t_info is None:
                self.logger.warning("Health check failed: terminal_info() returned None")
                self.is_connected = False
                return result

            result["connected"] = True
            result["terminal_connected"] = bool(t_info.connected)
            result["trade_allowed"] = bool(t_info.trade_allowed)

            a_info = mt5.account_info()
            if a_info is not None:
                result["account_login"] = a_info.login
                result["balance"] = a_info.balance
                result["equity"] = a_info.equity

            self.is_connected = result["connected"]

        except Exception as e:
            self.logger.error(f"Health check exception: {e}")
            self.is_connected = False

        return result

    # ------------------------------------------------------------------
    # Account info accessors
    # ------------------------------------------------------------------
    def get_account_summary(self) -> AccountSummary:
        """
        Fetch fresh account info from MT5.

        Returns:
            Updated AccountSummary.
        """
        self.account = self._fetch_account_info()
        return self.account

    def get_balance(self) -> float:
        """Get current account balance."""
        info = mt5.account_info()
        return info.balance if info else 0.0

    def get_equity(self) -> float:
        """Get current account equity."""
        info = mt5.account_info()
        return info.equity if info else 0.0

    def get_free_margin(self) -> float:
        """Get current free margin."""
        info = mt5.account_info()
        return info.margin_free if info else 0.0

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------
    def _initialize(self) -> None:
        """Initialize the MT5 terminal."""
        self.logger.info("Initializing MT5 terminal...")

        init_kwargs: Dict[str, Any] = {}
        if self.cfg.mt5.path:
            init_kwargs["path"] = self.cfg.mt5.path

        if not mt5.initialize(**init_kwargs):
            error_code, error_msg = mt5.last_error()
            msg = f"MT5 initialize() failed: [{error_code}] {error_msg}"
            self.logger.error(msg)
            raise MT5ConnectionError(msg)

        self.logger.info("MT5 terminal initialized")

    def _login(self) -> None:
        """Log in to the MT5 account."""
        login = self.cfg.mt5.login
        password = self.cfg.mt5.password
        server = self.cfg.mt5.server

        if login == 0 or not password or not server:
            raise MT5LoginError(
                "MT5 credentials incomplete — set MT5_LOGIN, MT5_PASSWORD, "
                "MT5_SERVER in your .env file"
            )

        self.logger.info(f"Logging in to MT5 account {login} on {server}...")

        if not mt5.login(login=login, password=password, server=server):
            error_code, error_msg = mt5.last_error()
            msg = f"MT5 login() failed: [{error_code}] {error_msg}"
            self.logger.error(msg)
            raise MT5LoginError(msg)

        self.logger.info(f"Logged in to account {login}")

    def _fetch_terminal_info(self) -> TerminalInfo:
        """Fetch and parse MT5 terminal information."""
        raw = mt5.terminal_info()
        if raw is None:
            self.logger.warning("terminal_info() returned None")
            return TerminalInfo()

        info = TerminalInfo(
            connected=bool(raw.connected),
            build=raw.build,
            name=raw.name,
            path=raw.path,
            data_path=raw.data_path,
            company=raw.company,
            trade_allowed=bool(raw.trade_allowed),
            community_account=bool(raw.community_account),
            community_connection=bool(raw.community_connection),
            raw=raw,
        )

        self.logger.info(f"Terminal: {info.name} (build {info.build})")
        self.logger.info(f"Broker  : {info.company}")
        self.logger.debug(f"Path    : {info.path}")
        self.logger.debug(f"Trading : {'Allowed' if info.trade_allowed else 'BLOCKED'}")

        return info

    def _fetch_account_info(self) -> AccountSummary:
        """Fetch and parse MT5 account information."""
        raw = mt5.account_info()
        if raw is None:
            error_code, error_msg = mt5.last_error()
            self.logger.warning(
                f"account_info() returned None: [{error_code}] {error_msg}"
            )
            return AccountSummary()

        margin_mode_id = raw.margin_mode
        margin_mode = MARGIN_MODE_NAMES.get(margin_mode_id, f"UNKNOWN({margin_mode_id})")
        trade_mode = TRADE_MODE_NAMES.get(raw.trade_mode, f"UNKNOWN({raw.trade_mode})")
        is_hedging = margin_mode_id == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING

        summary = AccountSummary(
            login=raw.login,
            name=raw.name,
            server=raw.server,
            company=raw.company,
            currency=raw.currency,
            balance=raw.balance,
            equity=raw.equity,
            margin=raw.margin,
            margin_free=raw.margin_free,
            margin_level=raw.margin_level if raw.margin_level else 0.0,
            leverage=raw.leverage,
            trade_mode=trade_mode,
            trade_allowed=bool(raw.trade_allowed),
            trade_expert=bool(raw.trade_expert),
            margin_mode=margin_mode,
            margin_mode_id=margin_mode_id,
            is_hedging=is_hedging,
            limit_orders=raw.limit_orders,
            raw=raw,
        )

        self._log_account_summary(summary)
        return summary

    def _log_account_summary(self, acct: AccountSummary) -> None:
        """Log a formatted account summary."""
        self.logger.info("=" * 50)
        self.logger.info("        MT5 ACCOUNT SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"  Login       : {acct.login}")
        self.logger.info(f"  Name        : {acct.name}")
        self.logger.info(f"  Broker      : {acct.company}")
        self.logger.info(f"  Server      : {acct.server}")
        self.logger.info(f"  Account Type: {acct.trade_mode}")
        self.logger.info(f"  Margin Mode : {acct.margin_mode}")
        self.logger.info(f"  Currency    : {acct.currency}")
        self.logger.info(f"  Leverage    : 1:{acct.leverage}")
        self.logger.info(f"  Balance     : {acct.balance:,.2f} {acct.currency}")
        self.logger.info(f"  Equity      : {acct.equity:,.2f} {acct.currency}")
        self.logger.info(f"  Free Margin : {acct.margin_free:,.2f} {acct.currency}")
        self.logger.info(f"  Margin Used : {acct.margin:,.2f} {acct.currency}")
        if acct.margin_level > 0:
            self.logger.info(f"  Margin Level: {acct.margin_level:.2f}%")
        self.logger.info(f"  Trade Allow : {'Yes' if acct.trade_allowed else 'NO'}")
        self.logger.info(f"  EA Allowed  : {'Yes' if acct.trade_expert else 'NO'}")
        self.logger.info(f"  Max Orders  : {acct.limit_orders}")
        self.logger.info("=" * 50)

    def _validate_account(self) -> None:
        """
        Validate account suitability for this bot.

        Checks:
          - Account is HEDGING (required for multi-position strategies)
          - Trading is allowed
          - Expert Advisors are allowed

        Raises:
            AccountTypeError: If account is NETTING and mode is LIVE.
        """
        if self.account is None:
            return

        # HEDGING check — critical
        if not self.account.is_hedging:
            msg = (
                f"HEDGING ACCOUNT REQUIRED -- NETTING ACCOUNT DETECTED\n"
                f"  Account {self.account.login} on {self.account.server} "
                f"is using {self.account.margin_mode} margin mode.\n"
                f"  This bot requires a HEDGING account to manage "
                f"multiple positions per symbol.\n"
                f"  Please switch to a HEDGING account or contact your "
                f"broker to change the margin mode."
            )

            if self.cfg.trading.mode == "LIVE":
                self.logger.error(msg)
                raise AccountTypeError(msg)
            else:
                self.logger.warning(
                    f"[DRY_RUN] {self.account.margin_mode} account detected. "
                    f"HEDGING is required for live trading. "
                    f"Continuing in DRY_RUN for testing."
                )

        # Trading permissions
        if not self.account.trade_allowed:
            self.logger.warning(
                "Trading is NOT allowed on this account. "
                "Check MetaTrader terminal settings."
            )

        if not self.account.trade_expert:
            self.logger.warning(
                "Expert Advisors (automated trading) are NOT allowed. "
                "Enable 'Allow algorithmic trading' in MT5 terminal: "
                "Tools > Options > Expert Advisors"
            )

        # Log final verdict
        if self.account.is_hedging and self.account.trade_allowed:
            self.logger.info(
                f"Account validated: {self.account.margin_mode} mode, "
                f"trading enabled"
            )
