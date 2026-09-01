"""
Tests for Dual Direction Strategy (Phase 6).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.execution_engine import ExecutionResult
from src.strategies.dual_direction import DualDirectionStrategy


@pytest.fixture
def mock_deps():
    cfg = MagicMock()
    df = MagicMock() # DataFetcher
    rm = MagicMock() # RiskManager
    ee = MagicMock() # ExecutionEngine
    
    # Mock Data
    df.get_current_tick.return_value = {"bid": 1.1000, "ask": 1.1002, "spread_points": 20}
    
    # Risk
    rm.calculate_sl_tp.side_effect = [
        (1.1005, 1.0975, 1.1065), # BUY
        (1.0995, 1.1025, 1.0935), # SELL
        (1.1005, 1.0975, 1.1065), # Refill Buy
        (1.0995, 1.1025, 1.0935), # Refill Sell
    ]
    rm.calculate_lot_size.return_value = 0.1
    
    # Execution
    ee.execute_market_order.side_effect = [
        ExecutionResult(success=True, ticket=100, fill_price=1.1005, volume_filled=0.1),
        ExecutionResult(success=True, ticket=101, fill_price=1.0995, volume_filled=0.1)
    ]
    
    return cfg, df, rm, ee


def test_execute_cycle_success(mock_deps):
    cfg, df, rm, ee = mock_deps
    strat = DualDirectionStrategy(cfg, df, rm, ee, logger=MagicMock())
    
    res = strat.execute_cycle("EURUSD")
    
    assert res is True
    assert "EURUSD" in strat.active_cycles
    
    cycle = strat.active_cycles["EURUSD"]
    assert cycle["buy_ticket"] == 100
    assert cycle["sell_ticket"] == 101
    
    assert ee.execute_market_order.call_count == 2
    assert rm.calculate_sl_tp.call_count == 4 # 2 for projection, 2 for post-fill lock


def test_orphan_buy_leg_closed_if_sell_fails(mock_deps):
    cfg, df, rm, ee = mock_deps
    
    ee.execute_market_order.side_effect = [
        ExecutionResult(success=True, ticket=100, fill_price=1.1005, volume_filled=0.1),
        ExecutionResult(success=False, error_detail="Mock Failure")
    ]
    
    strat = DualDirectionStrategy(cfg, df, rm, ee, logger=MagicMock())
    res = strat.execute_cycle("EURUSD")
    
    assert res is False
    assert "EURUSD" not in strat.active_cycles
    
    # Verified it closed the orphaned buy leg at index 100
    ee.close_position.assert_called_once()
    assert ee.close_position.call_args[0][0] == 100


def test_monitor_cycle_buy_tp(mock_deps):
    cfg, df, rm, ee = mock_deps
    strat = DualDirectionStrategy(cfg, df, rm, ee, logger=MagicMock())
    
    strat.execute_cycle("EURUSD")
    ee.close_position.reset_mock()
    
    # Simulate market moving UP to BUY TP (which is checked against Bid)
    # Target was 1.1065
    df.get_current_tick.return_value = {"bid": 1.1066, "ask": 1.1068}
    
    strat.monitor_cycle("EURUSD")
    
    # Should close both
    assert ee.close_position.call_count == 2
    assert "EURUSD" not in strat.active_cycles


def test_monitor_cycle_sell_sl(mock_deps):
    cfg, df, rm, ee = mock_deps
    strat = DualDirectionStrategy(cfg, df, rm, ee, logger=MagicMock())
    
    strat.execute_cycle("EURUSD")
    ee.close_position.reset_mock()
    
    # Simulate market moving UP to SELL SL (checked against Ask)
    # Target was 1.1025
    df.get_current_tick.return_value = {"bid": 1.1024, "ask": 1.1026}
    
    strat.monitor_cycle("EURUSD")
    
    # Should close both
    assert ee.close_position.call_count == 2
    assert "EURUSD" not in strat.active_cycles
