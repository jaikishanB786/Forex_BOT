"""
Data Fetcher — Retrieves market data from MetaTrader 5.

Responsibilities:
  - Support configurable broker symbol mapping (e.g. EURUSD -> EURUSD.pro).
  - Select symbols in Market Watch.
  - Fetch detailed symbol information (spread, lot sizes, digits, stop/freeze levels).
  - Fetch historical OHLCV candle data as pandas DataFrames.
  - Fetch recent tick data with stale-price detection.

Usage:
    from src.data_fetcher import MT5DataFetcher
    from src.config import load_config
    cfg = load_config()
    fetcher = MT5DataFetcher(cfg)
    info = fetcher.get_symbol_info("EURUSD")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import MetaTrader5 as mt5
import pandas as pd

from src.config import BotConfig
from src.logger import get_logger


# ---------------------------------------------------------------------------
# Constants & Mappings
# ---------------------------------------------------------------------------
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SymbolInfo:
    """Detailed information about a trading symbol."""
    name: str = ""
    description: str = ""
    digits: int = 0
    spread: int = 0                # Broker reported spread in points
    trade_calc_mode: int = 0
    trade_mode: int = 0
    volume_min: float = 0.0
    volume_max: float = 0.0
    volume_step: float = 0.0
    point: float = 0.0
    tick_size: float = 0.0
    tick_value: float = 0.0
    contract_size: float = 0.0     # Value of one standard lot
    margin_initial: float = 0.0
    margin_maintenance: float = 0.0
    trade_stops_level: int = 0     # Minimum distance in points for SL/TP
    trade_freeze_level: int = 0    # Distance in points to freeze order modification
    session_deals: int = 0
    raw: Optional[Any] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class DataFetchError(Exception):
    """Raised when data retrieval from MT5 fails."""
    pass


class SymbolNotFoundError(Exception):
    """Raised when a requested symbol does not exist or cannot be selected."""
    pass


class StaleMarketDataError(Exception):
    """Raised when market data is too old."""
    pass


# ---------------------------------------------------------------------------
# Fetcher class
# ---------------------------------------------------------------------------
class MT5DataFetcher:
    """Retrieves and formats market data from MetaTrader 5."""

    def __init__(self, cfg: BotConfig, logger: Optional[logging.Logger] = None):
        self.cfg = cfg
        self.logger = logger or get_logger()

    def map_symbol(self, symbol: str) -> str:
        """
        Map a canonical symbol (e.g., 'EURUSD') to the broker's specific symbol (e.g., 'EURUSD.pro').
        """
        return self.cfg.trading.symbol_mapping.get(symbol, symbol)

    def select_symbol(self, base_symbol: str) -> bool:
        """
        Ensure the mapped symbol is selected in the MT5 Market Watch.

        Args:
            base_symbol: The generic symbol name (e.g., "EURUSD").

        Returns:
            True if selected successfully, False otherwise.
        """
        broker_symbol = self.map_symbol(base_symbol)
        info = mt5.symbol_info(broker_symbol)
        
        if info is None:
            self.logger.error(f"Mapped symbol '{broker_symbol}' not found on broker.")
            return False

        if not info.visible:
            if not mt5.symbol_select(broker_symbol, True):
                self.logger.error(f"Failed to select '{broker_symbol}' in Market Watch.")
                return False
        
        return True

    def get_symbol_info(self, base_symbol: str) -> SymbolInfo:
        """
        Fetch detailed information for a symbol.

        Args:
            base_symbol: The generic symbol name.

        Returns:
            SymbolInfo dataclass.

        Raises:
            SymbolNotFoundError: If the symbol cannot be found or selected.
        """
        broker_symbol = self.map_symbol(base_symbol)
        
        if not self.select_symbol(base_symbol):
            raise SymbolNotFoundError(f"Cannot retrieve info for missing symbol: {broker_symbol}")

        raw = mt5.symbol_info(broker_symbol)
        if raw is None:
            raise SymbolNotFoundError(f"symbol_info returned None for {broker_symbol}")

        return SymbolInfo(
            name=raw.name,
            description=raw.description,
            digits=raw.digits,
            spread=raw.spread,
            trade_calc_mode=raw.trade_calc_mode,
            trade_mode=raw.trade_mode,
            volume_min=raw.volume_min,
            volume_max=raw.volume_max,
            volume_step=raw.volume_step,
            point=raw.point,
            tick_size=getattr(raw, 'trade_tick_size', 0.0),
            tick_value=getattr(raw, 'trade_tick_value', 0.0),
            contract_size=getattr(raw, 'trade_contract_size', 0.0),
            margin_initial=getattr(raw, 'margin_initial', 0.0),
            margin_maintenance=getattr(raw, 'margin_maintenance', 0.0),
            trade_stops_level=raw.trade_stops_level,
            trade_freeze_level=getattr(raw, 'trade_freeze_level', 0),
            session_deals=getattr(raw, 'session_deals', 0),
            raw=raw,
        )

    def get_candles(
        self, base_symbol: str, timeframe: str, count: int, 
        start_pos: int = 0
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candle data as a pandas DataFrame.

        Args:
            base_symbol: The generic symbol name.
            timeframe: Timeframe string (e.g., "M15", "H1").
            count: Number of candles to fetch.
            start_pos: Initial bar index (0 = current active bar).

        Returns:
            DataFrame with columns [time, open, high, low, close, tick_volume, spread, real_volume].
            The 'time' column is converted to a datetime (UTC).

        Raises:
            ValueError: If the timeframe string is invalid.
            DataFetchError: If no data is returned.
            SymbolNotFoundError: If the symbol is invalid.
        """
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        broker_symbol = self.map_symbol(base_symbol)
        if not self.select_symbol(base_symbol):
            raise SymbolNotFoundError(f"Symbol {broker_symbol} unavailable.")

        tf_code = TIMEFRAME_MAP[timeframe]
        rates = mt5.copy_rates_from_pos(broker_symbol, tf_code, start_pos, count)

        if rates is None or len(rates) == 0:
            error_code, error_msg = mt5.last_error()
            msg = f"Failed to fetch rates for {broker_symbol} ({timeframe}): [{error_code}] {error_msg}"
            self.logger.error(msg)
            raise DataFetchError(msg)

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        return df

    def get_current_tick(self, base_symbol: str) -> Dict[str, float]:
        """
        Fetch the most recent tick (bid/ask). Includes spread calculation.
        Validates whether the incoming tick is fresh.

        Args:
            base_symbol: The generic symbol name.

        Returns:
            Dictionary with 'time', 'bid', 'ask', 'last', 'volume', 'spread_points'.

        Raises:
            SymbolNotFoundError: If the symbol cannot be found or selected.
            DataFetchError: If mt5 fails to return a tick.
            StaleMarketDataError: If the latest tick timestamp is older than `stale_tick_seconds`.
        """
        broker_symbol = self.map_symbol(base_symbol)
        if not self.select_symbol(base_symbol):
            raise SymbolNotFoundError(f"Symbol {broker_symbol} unavailable.")

        tick = mt5.symbol_info_tick(broker_symbol)
        if tick is None:
            error_code, error_msg = mt5.last_error()
            msg = f"Failed to fetch tick for {broker_symbol}: [{error_code}] {error_msg}"
            self.logger.error(msg)
            raise DataFetchError(msg)
            
        current_time = time.time()
        elapsed = current_time - tick.time
        
        if elapsed > self.cfg.trading.stale_tick_seconds:
            msg = f"Stale market data for {broker_symbol}. Tick is {elapsed:.1f}s old (limit {self.cfg.trading.stale_tick_seconds}s)."
            self.logger.error(msg)
            raise StaleMarketDataError(msg)

        # Dynamic spread in points (ask - bid) / point
        sym_info = self.get_symbol_info(base_symbol)
        point = sym_info.point if sym_info.point > 0 else 0.00001
        
        bid = tick.bid
        ask = tick.ask
        spread_points = (ask - bid) / point

        return {
            "time": tick.time,
            "bid": bid,
            "ask": ask,
            "last": getattr(tick, 'last', 0.0),
            "volume": getattr(tick, 'volume', 0.0),
            "spread_points": spread_points,
            "broker_symbol": broker_symbol,
        }
