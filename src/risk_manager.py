"""
Risk Manager — Handles trade sizing, margin validation, and price calculations.

Responsibilities:
  - Calculate lot sizes (Risk % vs Fixed) with broker normalization.
  - Calculate precise Stop Loss and Take Profit levels (1:2 R:R handling).
  - Apply slippage and check spreads.
  - Validate available margin.
  - Validate daily drawdown rules.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple, Dict, Any

from src.config import BotConfig
from src.data_fetcher import SymbolInfo
from src.logger import get_logger


class RiskViolationError(Exception):
    """Raised when a trade violates a hard risk condition."""
    pass


class RiskManager:
    def __init__(self, cfg: BotConfig, logger: Optional[logging.Logger] = None):
        self.cfg = cfg
        self.logger = logger or get_logger()

    def normalize_volume(self, raw_volume: float, sym_info: SymbolInfo) -> float:
        """
        Normalize volume to broker constraints (min, max, step).

        Args:
            raw_volume: Unrounded calculated optimal volume.
            sym_info: Broker's constraints for the symbol.

        Returns:
            Properly rounded float volume.
        """
        if raw_volume < sym_info.volume_min:
            return sym_info.volume_min
            
        if raw_volume > sym_info.volume_max:
            return sym_info.volume_max
            
        step = sym_info.volume_step
        if step <= 0:
            return round(raw_volume, 2)
            
        # Standard rounding to the nearest volume step
        steps = round(raw_volume / step)
        normalized = steps * step
        
        # Avoid floating point funkiness (e.g., 0.150000000002)
        decimals = len(str(step).split('.')[-1]) if '.' in str(step) else 2
        return round(normalized, decimals)

    def calculate_lot_size(
        self, 
        account_balance: float, 
        entry_price: float, 
        sl_price: float, 
        sym_info: SymbolInfo
    ) -> float:
        """
        Determine the lot size for a trade.
        
        Uses cfg.risk.use_fixed_lot. If False, calculates dynamically based on:
        Risk Amount = Balance * Max_Risk_Pct
        Risk Size = |Entry - SL|
        Volume = Risk Amount / (Risk Size in Points * Tick Value / Tick Size)

        Args:
            account_balance: Current account balance.
            entry_price: Planned entry price.
            sl_price: Planned stop loss price.
            sym_info: Symbol constraints.

        Returns:
            Normalized lot size.
        """
        if self.cfg.risk.use_fixed_lot:
            return self.normalize_volume(self.cfg.risk.fixed_lot_size, sym_info)

        risk_pct = self.cfg.risk.max_risk_per_trade
        risk_cash = account_balance * risk_pct

        price_diff = abs(entry_price - sl_price)
        if price_diff <= 0:
            self.logger.warning(f"Calculated SL distance is <= 0. Falling back to minimum volume.")
            return sym_info.volume_min

        # Prevent div zero
        tick_size = sym_info.tick_size if sym_info.tick_size > 0 else sym_info.point
        tick_value = sym_info.tick_value if sym_info.tick_value > 0 else 1.0

        diff_in_points = price_diff / sym_info.point
        
        # Risk per 1 standard lot = points * (tick value per tick size ratio)
        risk_per_lot = diff_in_points * (tick_value / (tick_size / sym_info.point))
        
        if risk_per_lot <= 0:
            return sym_info.volume_min
            
        raw_volume = risk_cash / risk_per_lot
        return self.normalize_volume(raw_volume, sym_info)

    def calculate_sl_tp(
        self, 
        order_type: int,  # mt5.ORDER_TYPE_BUY or mt5.ORDER_TYPE_SELL
        entry_price: float, 
        sym_info: SymbolInfo,
        sl_points: Optional[int] = None,
        tp_points: Optional[int] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate Entry (w/ Slippage), SL, and TP (1:2 format if TP unspecified).
        
        BUY: Risk = Entry - SL, TP = Entry + (Risk * 2)  [or specific points]
        SELL: Risk = SL - Entry, TP = Entry - (Risk * 2) [or specific points]
        
        Slippage is strictly adverse (BUY entry goes UP, SELL entry goes DOWN).
        
        Returns:
            (Final Entry, Final SL, Final TP)
        """
        slippage = self.cfg.risk.slippage_points * sym_info.point
        
        sl_pts = sl_points or self.cfg.risk.default_sl_pips * 10
        tp_pts = tp_points or self.cfg.risk.default_tp_pips * 10
        
        if order_type == 0:  # mt5.ORDER_TYPE_BUY
            final_entry = entry_price + slippage
            sl = final_entry - (sl_pts * sym_info.point)
            
            # Enforce Broker stops_level minimums
            min_stop_distance = sym_info.trade_stops_level * sym_info.point
            if abs(final_entry - sl) < min_stop_distance:
                sl = final_entry - min_stop_distance
                
            # If no explicit TP provided, ensure 1:2 R:R from the final SL
            if tp_points is None:
                risk_amt = final_entry - sl
                tp = final_entry + (risk_amt * 2)
            else:
                tp = final_entry + (tp_pts * sym_info.point)
                
        else:                # mt5.ORDER_TYPE_SELL
            final_entry = entry_price - slippage
            sl = final_entry + (sl_pts * sym_info.point)
            
            # Enforce Broker stops_level minimums
            min_stop_distance = sym_info.trade_stops_level * sym_info.point
            if abs(final_entry - sl) < min_stop_distance:
                sl = final_entry + min_stop_distance
                
            if tp_points is None:
                risk_amt = sl - final_entry
                tp = final_entry - (risk_amt * 2)
            else:
                tp = final_entry - (tp_pts * sym_info.point)

        # Round all to proper digits
        final_entry = round(final_entry, sym_info.digits)
        sl = round(sl, sym_info.digits)
        tp = round(tp, sym_info.digits)
        
        return final_entry, sl, tp

    def check_spread(self, current_spread_points: float, symbol: str) -> None:
        """
        Block execution if spread exceeds configuration threshold.
        """
        max_spread = self.cfg.risk.max_spread_points
        if current_spread_points > max_spread:
            msg = f"Spread {current_spread_points:.1f}pts on {symbol} exceeds max allowed ({max_spread}pts)."
            raise RiskViolationError(msg)

    def check_daily_drawdown(self, starting_balance: float, current_equity: float) -> None:
        """
        Block execution if account equity falls below the max daily drawdown percentage.
        """
        if starting_balance <= 0:
            return
            
        dd_pct = (starting_balance - current_equity) / starting_balance
        max_dd = self.cfg.risk.max_daily_drawdown
        
        if dd_pct >= max_dd:
            msg = f"Max Daily Drawdown hit: {dd_pct*100:.2f}% >= {max_dd*100:.2f}%. Execution blocked."
            raise RiskViolationError(msg)

    def validate_margin(self, free_margin: float, required_margin: float) -> None:
        """
        Validate enough margin exists before entry.
        """
        if required_margin > free_margin:
            msg = f"Insufficient Margin: Need {required_margin:.2f}, only {free_margin:.2f} free."
            raise RiskViolationError(msg)
