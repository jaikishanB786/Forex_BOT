"""
Tests for the Execution Engine (src/execution_engine.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from src.config import BotConfig, TradingConfig, RiskConfig
from src.execution_engine import ExecutionEngine, ExecutionResult


MT5_MODULE = "src.execution_engine.mt5"


@pytest.fixture
def live_cfg():
    return BotConfig(
        trading=TradingConfig(mode="LIVE", magic_number=9999),
        risk=RiskConfig(slippage_points=5)
    )

@pytest.fixture
def dry_cfg():
    return BotConfig(
        trading=TradingConfig(mode="DRY_RUN", magic_number=9999),
        risk=RiskConfig(slippage_points=5)
    )


class TestExecutionEngine:
    def test_dry_run_bypasses_mt5(self, dry_cfg):
        engine = ExecutionEngine(dry_cfg)
        
        with patch(MT5_MODULE) as mock_mt5:
            res = engine.execute_market_order(
                symbol="EURUSD", volume=0.1, is_buy=True, 
                price=1.1000, sl=1.0950, tp=1.1100, comment="Test"
            )
            
            # Since it's DRY_RUN, order_send should never be called
            mock_mt5.order_send.assert_not_called()
            
            assert res.success is True
            assert "Test [DRY]" in res.comment
            assert res.fill_price == 1.1000

    @patch("time.sleep", return_value=None)
    def test_live_execution_success(self, mock_sleep, live_cfg):
        engine = ExecutionEngine(live_cfg)
        
        with patch(MT5_MODULE) as mock_mt5:
            # Setup successful order
            mock_result = SimpleNamespace(
                retcode=10009, # TRADE_RETCODE_DONE
                order=123456,
                price=1.1001,
                volume=0.1
            )
            mock_mt5.order_send.return_value = mock_result
            mock_mt5.TRADE_RETCODE_DONE = 10009
            
            # Setup position verification success
            mock_mt5.positions_get.return_value = [SimpleNamespace(ticket=123456, identifier=123456)]
            
            # MT5 Constants
            mock_mt5.ORDER_FILLING_FOK = 0
            
            res = engine.execute_market_order(
                symbol="EURUSD", volume=0.1, is_buy=True, 
                price=1.1000, sl=1.0950, tp=1.1100, comment="Test"
            )
            
            assert res.success is True
            assert res.ticket == 123456
            assert res.fill_price == 1.1001
            assert res.volume_filled == 0.1
            
            # Test caching of filling mode
            assert engine._filling_modes["EURUSD"] == 0

    @patch("time.sleep", return_value=None)
    def test_filling_mode_fallback(self, mock_sleep, live_cfg):
        """
        Tests if the engine correctly falls back to IOC if FOK fails, 
        and caches the successful mode for the next execution.
        """
        engine = ExecutionEngine(live_cfg)
        
        with patch(MT5_MODULE) as mock_mt5:
            # Constants
            mock_mt5.ORDER_FILLING_FOK = 0
            mock_mt5.ORDER_FILLING_IOC = 1
            mock_mt5.ORDER_FILLING_RETURN = 2
            mock_mt5.TRADE_RETCODE_DONE = 10009
            mock_mt5.TRADE_RETCODE_INVALID_FILL = 10030
            
            # Request 1: Fail (Invalid Fill)
            res1 = SimpleNamespace(retcode=10030, comment="Invalid fill")
            # Request 2: Success
            res2 = SimpleNamespace(retcode=10009, order=777, price=1.1, volume=0.1)
            
            mock_mt5.order_send.side_effect = [res1, res2]
            mock_mt5.last_error.return_value = (10030, "Invalid fill")
            mock_mt5.positions_get.return_value = [SimpleNamespace(ticket=777, identifier=777)]
            
            res = engine.execute_market_order("EURUSD", 0.1, True, 1.1, 0, 0)
            
            assert mock_mt5.order_send.call_count == 2
            
            # Verify the type_filling changed from FOK (0) to IOC (1)
            call1_args = mock_mt5.order_send.call_args_list[0][0][0]
            call2_args = mock_mt5.order_send.call_args_list[1][0][0]
            assert call1_args["type_filling"] == 0
            assert call2_args["type_filling"] == 1
            
            assert res.success is True
            assert engine._filling_modes["EURUSD"] == 1

    @patch("time.sleep", return_value=None)
    def test_post_trade_verification_failure(self, mock_sleep, live_cfg):
        """
        If order_send returns DONE but mt5.positions_get doesn't find the ticket,
        it should fail securely without hallucinating a fill.
        """
        engine = ExecutionEngine(live_cfg)
        
        with patch(MT5_MODULE) as mock_mt5:
            mock_result = SimpleNamespace(retcode=10009, order=999, price=1.1, volume=0.1)
            mock_mt5.order_send.return_value = mock_result
            mock_mt5.TRADE_RETCODE_DONE = 10009
            
            # Missing from positions AND history
            mock_mt5.positions_get.return_value = None
            mock_mt5.history_deals_get.return_value = None
            
            res = engine.execute_market_order("EURUSD", 0.1, True, 1.1, 0, 0)
            
            assert res.success is False
            assert "not found" in res.error_detail

    @patch("time.sleep", return_value=None)
    def test_hard_rejection_margin(self, mock_sleep, live_cfg):
        """
        Tests that terminal margin errors correctly break the retry loop immediately.
        """
        engine = ExecutionEngine(live_cfg)
        
        with patch(MT5_MODULE) as mock_mt5:
            # 10019 = TRADE_RETCODE_NO_MONEY
            mock_mt5.order_send.return_value = SimpleNamespace(retcode=10019)
            mock_mt5.TRADE_RETCODE_NO_MONEY = 10019
            mock_mt5.TRADE_RETCODE_TRADE_DISABLED = 10018
            mock_mt5.TRADE_RETCODE_MARKET_CLOSED = 10018
            mock_mt5.TRADE_RETCODE_INVALID_FILL = 10030
            
            mock_mt5.last_error.return_value = (10019, "No money")
            
            res = engine.execute_market_order("EURUSD", 100.0, True, 1.1, 0, 0)
            
            # Since it's a hard block, it should NOT retry
            assert mock_mt5.order_send.call_count == 1
            assert res.success is False
