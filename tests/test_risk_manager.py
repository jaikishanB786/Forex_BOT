"""
Tests for the Risk Manager (src/risk_manager.py).
"""

from __future__ import annotations

import pytest

from src.config import BotConfig, TradingConfig, RiskConfig
from src.data_fetcher import SymbolInfo
from src.risk_manager import RiskManager, RiskViolationError


@pytest.fixture
def risk_cfg():
    return BotConfig(
        trading=TradingConfig(mode="DRY_RUN"),
        risk=RiskConfig(
            max_risk_per_trade=0.01,
            use_fixed_lot=False,
            fixed_lot_size=0.1,
            max_daily_drawdown=0.05,
            default_sl_pips=30,
            default_tp_pips=60,
            max_spread_points=20,
            slippage_points=5
        )
    )


@pytest.fixture
def eurusd_info():
    return SymbolInfo(
        name="EURUSD",
        digits=5,
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        trade_stops_level=10,
    )


class TestRiskManagerVolume:
    def test_normalize_volume_min_max(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        assert rm.normalize_volume(0.005, eurusd_info) == 0.01  # Rounds to min
        assert rm.normalize_volume(150.0, eurusd_info) == 100.0 # Caps at max
        
    def test_normalize_volume_step(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        assert rm.normalize_volume(0.123, eurusd_info) == 0.12
        assert rm.normalize_volume(0.126, eurusd_info) == 0.13

    def test_calculate_lot_size_fixed(self, risk_cfg, eurusd_info):
        risk_cfg.risk.use_fixed_lot = True
        risk_cfg.risk.fixed_lot_size = 0.5
        rm = RiskManager(risk_cfg)
        lot = rm.calculate_lot_size(10000, 1.1000, 1.0970, eurusd_info)
        assert lot == 0.5

    def test_calculate_lot_size_pct(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        # $10,000 balance * 1% risk = $100 risk
        # 1.1000 - 1.0970 = 30 pips = 300 points
        # 300 points * $1 tick value = $300 risk per standard lot
        # Volume = 100 / 300 = 0.33 lots
        lot = rm.calculate_lot_size(10000.0, 1.10000, 1.09700, eurusd_info)
        assert lot == 0.33

    def test_calculate_lot_size_zero_sl_distance(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        # Entry == SL should fallback to minimum volume to prevent div-zero
        lot = rm.calculate_lot_size(10000.0, 1.10000, 1.10000, eurusd_info)
        assert lot == eurusd_info.volume_min


class TestRiskManagerSlTp:
    def test_calculate_sl_tp_buy_default(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        # Entry 1.10000 + 5 slippage pts = 1.10005
        # SL = 300 pts (30 pips) = 1.09705
        # TP = final_entry + (risk * 2) = 1.10005 + (0.00300 * 2) = 1.10605
        entry, sl, tp = rm.calculate_sl_tp(0, 1.10000, eurusd_info)
        
        assert entry == 1.10005
        assert sl == 1.09705
        assert tp == 1.10605

    def test_calculate_sl_tp_sell_default(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        # Entry 1.10000 - 5 slippage pts = 1.09995
        # SL = 300 pts (30 pips) = 1.10295
        # TP = final_entry - (risk * 2) = 1.09995 - (0.00300 * 2) = 1.09395
        entry, sl, tp = rm.calculate_sl_tp(1, 1.10000, eurusd_info)
        
        assert entry == 1.09995
        assert sl == 1.10295
        assert tp == 1.09395

    def test_calculate_sl_tp_broker_stops_level(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        eurusd_info.trade_stops_level = 500  # 50 pips minimum stop limit
        
        # We requested a 30 pip stop (300 points), which is under the 500 minimum.
        # It should override SL to 500 points away.
        entry, sl, tp = rm.calculate_sl_tp(0, 1.10000, eurusd_info, sl_points=300)
        
        # 1.10005 is entry. SL goes to 1.10005 - 500 pts = 1.09505
        # Risk = 500 pts. TP = 1.10005 + 1000 pts = 1.11005
        assert sl == 1.09505
        assert tp == 1.11005

    def test_calculate_sl_tp_custom_points(self, risk_cfg, eurusd_info):
        rm = RiskManager(risk_cfg)
        # Passed explicitly 20 pips (200 points) and 100 pips (1000 points)
        entry, sl, tp = rm.calculate_sl_tp(0, 1.10000, eurusd_info, sl_points=200, tp_points=1000)
        
        assert entry == 1.10005
        assert sl == 1.09805
        assert tp == 1.11005


class TestRiskManagerValidations:
    def test_check_spread_pass(self, risk_cfg):
        rm = RiskManager(risk_cfg)
        rm.check_spread(15.0, "EURUSD")  # 15 < 20 max

    def test_check_spread_fail(self, risk_cfg):
        rm = RiskManager(risk_cfg)
        with pytest.raises(RiskViolationError, match="exceeds max allowed"):
            rm.check_spread(25.0, "EURUSD")

    def test_check_daily_drawdown_pass(self, risk_cfg):
        rm = RiskManager(risk_cfg)
        rm.check_daily_drawdown(10000.0, 9600.0)  # -4% DD (max is 5%)

    def test_check_daily_drawdown_fail(self, risk_cfg):
        rm = RiskManager(risk_cfg)
        # Drop is exactly 5% (max allowed)
        with pytest.raises(RiskViolationError, match="Max Daily Drawdown hit"):
            rm.check_daily_drawdown(10000.0, 9500.0)

    def test_validate_margin_pass(self, risk_cfg):
        rm = RiskManager(risk_cfg)
        rm.validate_margin(1000.0, 500.0)

    def test_validate_margin_fail(self, risk_cfg):
        rm = RiskManager(risk_cfg)
        with pytest.raises(RiskViolationError, match="Insufficient Margin"):
            rm.validate_margin(500.0, 2000.0)
