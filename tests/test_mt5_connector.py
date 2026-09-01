"""
Tests for the MT5 Connector (src/mt5_connector.py).

All MT5 calls are mocked — no live terminal required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.config import BotConfig, MT5Config, TradingConfig, LoggingConfig
from src.mt5_connector import (
    MT5Connector,
    MT5ConnectionError,
    MT5LoginError,
    AccountTypeError,
    AccountSummary,
    TerminalInfo,
)


# ---------------------------------------------------------------------------
# Fixtures: reusable mock data
# ---------------------------------------------------------------------------
MT5_MODULE = "src.mt5_connector.mt5"

# MT5 margin mode constants (mirrored from MetaTrader5 package)
MARGIN_MODE_NETTING = 0
MARGIN_MODE_EXCHANGE = 1
MARGIN_MODE_HEDGING = 2

# MT5 trade mode constants
TRADE_MODE_DEMO = 0
TRADE_MODE_CONTEST = 1
TRADE_MODE_REAL = 2


def _make_terminal_info(**overrides) -> SimpleNamespace:
    """Build a fake terminal_info() result."""
    defaults = {
        "connected": True,
        "build": 4150,
        "name": "MetaTrader 5",
        "path": r"C:\Program Files\MetaTrader 5",
        "data_path": r"C:\Users\test\AppData\Roaming\MetaQuotes",
        "company": "TestBroker Ltd",
        "trade_allowed": True,
        "community_account": False,
        "community_connection": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_account_info(**overrides) -> SimpleNamespace:
    """Build a fake account_info() result."""
    defaults = {
        "login": 12345678,
        "name": "Test Trader",
        "server": "TestBroker-Demo",
        "company": "TestBroker Ltd",
        "currency": "USD",
        "balance": 10000.0,
        "equity": 10000.0,
        "margin": 0.0,
        "margin_free": 10000.0,
        "margin_level": 0.0,
        "leverage": 100,
        "trade_mode": TRADE_MODE_DEMO,
        "trade_allowed": True,
        "trade_expert": True,
        "margin_mode": MARGIN_MODE_HEDGING,
        "limit_orders": 200,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_config(mode: str = "DRY_RUN", **mt5_overrides) -> BotConfig:
    """Create a BotConfig suitable for testing."""
    mt5_defaults = {
        "login": 12345678,
        "password": "test_pass",
        "server": "TestBroker-Demo",
    }
    mt5_defaults.update(mt5_overrides)
    return BotConfig(
        mt5=MT5Config(**mt5_defaults),
        trading=TradingConfig(mode=mode),
        logging=LoggingConfig(level="WARNING", log_to_file=False),
    )


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------
class TestMT5Initialize:
    @patch(MT5_MODULE)
    def test_successful_initialize(self, mock_mt5):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = _make_terminal_info()
        mock_mt5.account_info.return_value = _make_account_info()
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = MARGIN_MODE_HEDGING
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = MARGIN_MODE_NETTING
        mock_mt5.ACCOUNT_MARGIN_MODE_EXCHANGE = MARGIN_MODE_EXCHANGE
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = TRADE_MODE_DEMO
        mock_mt5.ACCOUNT_TRADE_MODE_CONTEST = TRADE_MODE_CONTEST
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = TRADE_MODE_REAL

        cfg = _make_config()
        connector = MT5Connector(cfg)
        result = connector.connect()

        assert connector.is_connected is True
        assert isinstance(result, AccountSummary)
        mock_mt5.initialize.assert_called_once()
        mock_mt5.login.assert_called_once()

    @patch(MT5_MODULE)
    def test_initialize_failure(self, mock_mt5):
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (-1, "Terminal not found")

        cfg = _make_config()
        connector = MT5Connector(cfg)

        with pytest.raises(MT5ConnectionError, match="initialize.*failed"):
            connector.connect()

        assert connector.is_connected is False


# ---------------------------------------------------------------------------
# Tests: Login
# ---------------------------------------------------------------------------
class TestMT5Login:
    @patch(MT5_MODULE)
    def test_login_failure(self, mock_mt5):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = False
        mock_mt5.last_error.return_value = (-2, "Invalid credentials")

        cfg = _make_config()
        connector = MT5Connector(cfg)

        with pytest.raises(MT5LoginError, match="login.*failed"):
            connector.connect()

    @patch(MT5_MODULE)
    def test_missing_credentials(self, mock_mt5):
        mock_mt5.initialize.return_value = True

        cfg = _make_config(login=0, password="", server="")
        connector = MT5Connector(cfg)

        with pytest.raises(MT5LoginError, match="credentials incomplete"):
            connector.connect()


# ---------------------------------------------------------------------------
# Tests: Terminal Info
# ---------------------------------------------------------------------------
class TestTerminalInfo:
    @patch(MT5_MODULE)
    def test_terminal_info_parsed(self, mock_mt5):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = _make_terminal_info(
            build=4200, company="MyBroker"
        )
        mock_mt5.account_info.return_value = _make_account_info()
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = MARGIN_MODE_HEDGING
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = MARGIN_MODE_NETTING
        mock_mt5.ACCOUNT_MARGIN_MODE_EXCHANGE = MARGIN_MODE_EXCHANGE
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = TRADE_MODE_DEMO
        mock_mt5.ACCOUNT_TRADE_MODE_CONTEST = TRADE_MODE_CONTEST
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = TRADE_MODE_REAL

        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.connect()

        assert connector.terminal is not None
        assert connector.terminal.build == 4200
        assert connector.terminal.company == "MyBroker"
        assert connector.terminal.connected is True

    @patch(MT5_MODULE)
    def test_terminal_info_none_returns_default(self, mock_mt5):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = None
        mock_mt5.account_info.return_value = _make_account_info()
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = MARGIN_MODE_HEDGING
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = MARGIN_MODE_NETTING
        mock_mt5.ACCOUNT_MARGIN_MODE_EXCHANGE = MARGIN_MODE_EXCHANGE
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = TRADE_MODE_DEMO
        mock_mt5.ACCOUNT_TRADE_MODE_CONTEST = TRADE_MODE_CONTEST
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = TRADE_MODE_REAL

        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.connect()

        assert connector.terminal is not None
        assert connector.terminal.connected is False


# ---------------------------------------------------------------------------
# Tests: Account Info
# ---------------------------------------------------------------------------
class TestAccountInfo:
    @patch(MT5_MODULE)
    def test_account_info_parsed(self, mock_mt5):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = _make_terminal_info()
        mock_mt5.account_info.return_value = _make_account_info(
            balance=50000.0,
            equity=49500.0,
            margin_free=48000.0,
            leverage=200,
            currency="EUR",
        )
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = MARGIN_MODE_HEDGING
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = MARGIN_MODE_NETTING
        mock_mt5.ACCOUNT_MARGIN_MODE_EXCHANGE = MARGIN_MODE_EXCHANGE
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = TRADE_MODE_DEMO
        mock_mt5.ACCOUNT_TRADE_MODE_CONTEST = TRADE_MODE_CONTEST
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = TRADE_MODE_REAL

        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.connect()

        acct = connector.account
        assert acct.balance == 50000.0
        assert acct.equity == 49500.0
        assert acct.margin_free == 48000.0
        assert acct.leverage == 200
        assert acct.currency == "EUR"
        assert acct.is_hedging is True
        assert acct.margin_mode == "HEDGING"
        assert acct.trade_mode == "DEMO"


# ---------------------------------------------------------------------------
# Tests: HEDGING vs NETTING validation
# ---------------------------------------------------------------------------
class TestAccountValidation:
    def _setup_mock(self, mock_mt5, margin_mode=MARGIN_MODE_HEDGING):
        """Common mock setup helper."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = _make_terminal_info()
        mock_mt5.account_info.return_value = _make_account_info(
            margin_mode=margin_mode
        )
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = MARGIN_MODE_HEDGING
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = MARGIN_MODE_NETTING
        mock_mt5.ACCOUNT_MARGIN_MODE_EXCHANGE = MARGIN_MODE_EXCHANGE
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = TRADE_MODE_DEMO
        mock_mt5.ACCOUNT_TRADE_MODE_CONTEST = TRADE_MODE_CONTEST
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = TRADE_MODE_REAL

    @patch(MT5_MODULE)
    def test_hedging_account_accepted(self, mock_mt5):
        self._setup_mock(mock_mt5, margin_mode=MARGIN_MODE_HEDGING)

        cfg = _make_config(mode="DRY_RUN")
        connector = MT5Connector(cfg)
        acct = connector.connect()

        assert acct.is_hedging is True
        assert acct.margin_mode == "HEDGING"

    @patch(MT5_MODULE)
    def test_netting_account_rejected_in_live_mode(self, mock_mt5):
        """NETTING + LIVE = AccountTypeError."""
        self._setup_mock(mock_mt5, margin_mode=MARGIN_MODE_NETTING)

        cfg = _make_config(mode="LIVE")
        connector = MT5Connector(cfg)

        with pytest.raises(AccountTypeError, match="HEDGING ACCOUNT REQUIRED"):
            connector.connect()

    @patch(MT5_MODULE)
    def test_netting_account_warned_in_dry_run(self, mock_mt5):
        """NETTING + DRY_RUN = warning but no exception."""
        self._setup_mock(mock_mt5, margin_mode=MARGIN_MODE_NETTING)

        cfg = _make_config(mode="DRY_RUN")
        connector = MT5Connector(cfg)
        acct = connector.connect()

        assert acct.is_hedging is False
        assert acct.margin_mode == "NETTING"
        assert connector.is_connected is True  # Still connected for dry-run

    @patch(MT5_MODULE)
    def test_exchange_account_rejected_in_live_mode(self, mock_mt5):
        """EXCHANGE + LIVE = AccountTypeError."""
        self._setup_mock(mock_mt5, margin_mode=MARGIN_MODE_EXCHANGE)

        cfg = _make_config(mode="LIVE")
        connector = MT5Connector(cfg)

        with pytest.raises(AccountTypeError, match="HEDGING ACCOUNT REQUIRED"):
            connector.connect()


# ---------------------------------------------------------------------------
# Tests: Health check
# ---------------------------------------------------------------------------
class TestHealthCheck:
    @patch(MT5_MODULE)
    def test_healthy_connection(self, mock_mt5):
        mock_mt5.terminal_info.return_value = _make_terminal_info()
        mock_mt5.account_info.return_value = _make_account_info(
            balance=5000.0, equity=4800.0
        )

        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.is_connected = True
        result = connector.health_check()

        assert result["connected"] is True
        assert result["terminal_connected"] is True
        assert result["trade_allowed"] is True
        assert result["balance"] == 5000.0
        assert result["equity"] == 4800.0

    @patch(MT5_MODULE)
    def test_unhealthy_connection(self, mock_mt5):
        mock_mt5.terminal_info.return_value = None

        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.is_connected = True
        result = connector.health_check()

        assert result["connected"] is False
        assert connector.is_connected is False


# ---------------------------------------------------------------------------
# Tests: Disconnect & Context Manager
# ---------------------------------------------------------------------------
class TestDisconnect:
    @patch(MT5_MODULE)
    def test_disconnect(self, mock_mt5):
        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.is_connected = True
        connector.disconnect()

        assert connector.is_connected is False
        mock_mt5.shutdown.assert_called_once()

    @patch(MT5_MODULE)
    def test_disconnect_when_not_connected(self, mock_mt5):
        cfg = _make_config()
        connector = MT5Connector(cfg)
        connector.is_connected = False
        connector.disconnect()

        # shutdown() should NOT be called if not connected
        mock_mt5.shutdown.assert_not_called()

    @patch(MT5_MODULE)
    def test_context_manager(self, mock_mt5):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = _make_terminal_info()
        mock_mt5.account_info.return_value = _make_account_info()
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = MARGIN_MODE_HEDGING
        mock_mt5.ACCOUNT_MARGIN_MODE_RETAIL_NETTING = MARGIN_MODE_NETTING
        mock_mt5.ACCOUNT_MARGIN_MODE_EXCHANGE = MARGIN_MODE_EXCHANGE
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = TRADE_MODE_DEMO
        mock_mt5.ACCOUNT_TRADE_MODE_CONTEST = TRADE_MODE_CONTEST
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = TRADE_MODE_REAL

        cfg = _make_config()
        with MT5Connector(cfg) as conn:
            assert conn.is_connected is True

        mock_mt5.shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Balance/Equity accessors
# ---------------------------------------------------------------------------
class TestAccessors:
    @patch(MT5_MODULE)
    def test_get_balance(self, mock_mt5):
        mock_mt5.account_info.return_value = _make_account_info(balance=7777.77)
        connector = MT5Connector(_make_config())
        assert connector.get_balance() == 7777.77

    @patch(MT5_MODULE)
    def test_get_equity(self, mock_mt5):
        mock_mt5.account_info.return_value = _make_account_info(equity=6666.66)
        connector = MT5Connector(_make_config())
        assert connector.get_equity() == 6666.66

    @patch(MT5_MODULE)
    def test_get_free_margin(self, mock_mt5):
        mock_mt5.account_info.return_value = _make_account_info(margin_free=5555.55)
        connector = MT5Connector(_make_config())
        assert connector.get_free_margin() == 5555.55

    @patch(MT5_MODULE)
    def test_accessors_return_zero_on_none(self, mock_mt5):
        mock_mt5.account_info.return_value = None
        connector = MT5Connector(_make_config())
        assert connector.get_balance() == 0.0
        assert connector.get_equity() == 0.0
        assert connector.get_free_margin() == 0.0
