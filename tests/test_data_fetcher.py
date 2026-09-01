"""
Tests for the MT5 Data Fetcher (src/data_fetcher.py).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data_fetcher import MT5DataFetcher, SymbolInfo, SymbolNotFoundError, DataFetchError, StaleMarketDataError
from src.config import BotConfig, TradingConfig

MT5_MODULE = "src.data_fetcher.mt5"


def _make_symbol_info(**overrides) -> SimpleNamespace:
    defaults = {
        "name": "EURUSD",
        "description": "Euro vs US Dollar",
        "digits": 5,
        "spread": 12,
        "trade_calc_mode": 0,
        "trade_mode": 4,
        "volume_min": 0.01,
        "volume_max": 500.0,
        "volume_step": 0.01,
        "point": 0.00001,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "trade_contract_size": 100000.0,
        "margin_initial": 0.0,
        "margin_maintenance": 0.0,
        "trade_stops_level": 50,
        "trade_freeze_level": 10,
        "session_deals": 5000,
        "visible": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_tick_info(**overrides) -> SimpleNamespace:
    defaults = {
        "time": time.time(),
        "bid": 1.10000,
        "ask": 1.10012,
        "last": 1.10005,
        "volume": 20.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_rates() -> np.ndarray:
    dtype = [
        ('time', '<i8'), ('open', '<f8'), ('high', '<f8'),
        ('low', '<f8'), ('close', '<f8'), ('tick_volume', '<i8'),
        ('spread', '<i4'), ('real_volume', '<i8')
    ]
    data = [
        (1690000000, 1.1000, 1.1050, 1.0950, 1.1020, 100, 10, 0),
        (1690000900, 1.1020, 1.1060, 1.1010, 1.1050, 150, 12, 0),
    ]
    return np.array(data, dtype=dtype)


@pytest.fixture
def test_cfg():
    return BotConfig(
        trading=TradingConfig(
            mode="DRY_RUN",
            symbol_mapping={"EURUSD": "EURUSD.pro"},
            stale_tick_seconds=300
        )
    )


class TestMT5DataFetcher:
    
    @patch(MT5_MODULE)
    def test_select_symbol_mapping(self, mock_mt5, test_cfg):
        mock_mt5.symbol_info.return_value = _make_symbol_info(visible=True)
        fetcher = MT5DataFetcher(test_cfg)
        
        assert fetcher.select_symbol("EURUSD") is True
        mock_mt5.symbol_info.assert_called_once_with("EURUSD.pro")

    @patch(MT5_MODULE)
    def test_get_symbol_info_advanced_properties(self, mock_mt5, test_cfg):
        mock_mt5.symbol_info.return_value = _make_symbol_info(
            trade_contract_size=100000.0,
            trade_freeze_level=25,
            trade_stops_level=30
        )
        fetcher = MT5DataFetcher(test_cfg)
        info = fetcher.get_symbol_info("EURUSD")
        
        assert info.contract_size == 100000.0
        assert info.trade_freeze_level == 25
        assert info.trade_stops_level == 30

    @patch(MT5_MODULE)
    def test_get_candles_success(self, mock_mt5, test_cfg):
        mock_mt5.symbol_info.return_value = _make_symbol_info()
        mock_mt5.copy_rates_from_pos.return_value = _make_rates()
        mock_mt5.TIMEFRAME_M15 = 15
        
        fetcher = MT5DataFetcher(test_cfg)
        df = fetcher.get_candles("EURUSD", "M15", 2)
        
        mock_mt5.copy_rates_from_pos.assert_called_once_with("EURUSD.pro", 15, 0, 2)
        assert len(df) == 2
        assert df["time"].dt.tz is not None  # Must be UTC aware

    @patch(MT5_MODULE)
    def test_get_current_tick_spread_calculation(self, mock_mt5, test_cfg):
        mock_mt5.symbol_info.return_value = _make_symbol_info(point=0.00001)
        # bid = 1.10000, ask = 1.10012 -> 12 points
        mock_mt5.symbol_info_tick.return_value = _make_tick_info(time=time.time())
        
        fetcher = MT5DataFetcher(test_cfg)
        tick = fetcher.get_current_tick("EURUSD")
        
        assert tick["spread_points"] == pytest.approx(12.0)
        assert tick["broker_symbol"] == "EURUSD.pro"

    @patch(MT5_MODULE)
    def test_get_current_tick_stale_data(self, mock_mt5, test_cfg):
        mock_mt5.symbol_info.return_value = _make_symbol_info()
        # Create a tick timestamp that is 10 minutes old
        old_time = time.time() - 600  
        mock_mt5.symbol_info_tick.return_value = _make_tick_info(time=old_time)
        
        fetcher = MT5DataFetcher(test_cfg)
        
        with pytest.raises(StaleMarketDataError, match="Stale market data"):
            fetcher.get_current_tick("EURUSD")
            
    @patch(MT5_MODULE)
    def test_get_current_tick_data_fetch_error(self, mock_mt5, test_cfg):
        mock_mt5.symbol_info.return_value = _make_symbol_info()
        mock_mt5.symbol_info_tick.return_value = None
        mock_mt5.last_error.return_value = (-1, "No data")

        fetcher = MT5DataFetcher(test_cfg)
        with pytest.raises(DataFetchError):
            fetcher.get_current_tick("EURUSD")
