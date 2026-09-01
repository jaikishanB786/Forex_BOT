"""
Execution Engine — Places, monitors, and validates MT5 trades.

Responsibilities:
  - DRY_RUN bypassing.
  - Safe retry loops on transient failures.
  - Dynamic filling mode discovery (FOK -> IOC -> RETURN).
  - Validates MT5 return codes.
  - Verifies position is actually opened via ticket confirmation.
  - Returns actual fill price.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict

import MetaTrader5 as mt5

from src.config import BotConfig
from src.logger import get_logger


@dataclass
class ExecutionResult:
    """Standardized response from the execution engine."""
    success: bool
    ticket: int = 0
    fill_price: float = 0.0
    volume_filled: float = 0.0
    comment: str = ""
    error_detail: str = ""


class ExecutionError(Exception):
    """Raised when an execution totally fails or exhausts retries."""
    pass


class ExecutionEngine:
    def __init__(self, cfg: BotConfig, logger: Optional[logging.Logger] = None):
        self.cfg = cfg
        self.logger = logger or get_logger()
        
        # Cache for successful filling mode per symbol
        # e.g., 'EURUSD': mt5.ORDER_FILLING_FOK
        self._filling_modes: Dict[str, int] = {}
        
        # The standard sequence to attempt
        self._filling_sequence = [
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_RETURN,
        ]

    def _get_filling_mode(self, symbol: str, attempt: int = 0) -> int:
        """
        Return the cached filling mode, or cycle through based on attempt number.
        """
        if symbol in self._filling_modes and attempt == 0:
            return self._filling_modes[symbol]
            
        # fallback through the sequence
        idx = attempt % len(self._filling_sequence)
        return self._filling_sequence[idx]

    def _verify_position(self, ticket: int, symbol: str) -> bool:
        """
        Checks MT5 to verify that a deal/position actually resulted from the ticket.
        """
        # A successful order_send returns an order ticket.
        # Check if the order is still open (meaning it's a pending limit order, not a market deal).
        # We only throw Market Orders, so the order should be historically filled and convert to a position.
        
        # Check live positions
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for p in positions:
                # MT5 position ticket doesn't strictly always equal order ticket,
                # but identifier helps, or we just trust the position list presence.
                # In MT5 Hedging, position ticket matches the initial order ticket that spawned it.
                if p.ticket == ticket or p.identifier == ticket:
                    return True
                    
        # Check history deals (if it closed immediately or for more strict checks)
        deals = mt5.history_deals_get(position=ticket)
        if deals and len(deals) > 0:
            return True
            
        return False

    def execute_market_order(
        self,
        symbol: str,
        volume: float,
        is_buy: bool,
        price: float,
        sl: float,
        tp: float,
        comment: str = "",
        max_retries: int = 3
    ) -> ExecutionResult:
        """
        Execute a market order with retry logic and filling mode discovery.
        """
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        side_str = "BUY" if is_buy else "SELL"
        deviation = self.cfg.risk.slippage_points
        magic = self.cfg.trading.magic_number

        self.logger.info(f"Targeting {side_str} {volume} {symbol} @ {price} (SL:{sl} TP:{tp})")

        # ---------------- DRY_RUN MODE ----------------
        if self.cfg.trading.mode != "LIVE":
            self.logger.info(f"[DRY_RUN] Simulated {side_str} execution successful.")
            return ExecutionResult(
                success=True,
                ticket=int(time.time()),  # Fake ticket
                fill_price=price,
                volume_filled=volume,
                comment=f"{comment} [DRY]"
            )
            
        # ---------------- LIVE MODE ----------------
        for attempt in range(max_retries):
            filling_mode = self._get_filling_mode(symbol, attempt)
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": deviation,
                "magic": magic,
                "comment": comment[:27],  # MT5 limit is ~31 chars
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            
            # Send the request
            result = mt5.order_send(request)
            
            if result is None:
                error_code, error_msg = mt5.last_error()
                self.logger.warning(
                    f"[{attempt+1}/{max_retries}] order_send returned None. "
                    f"Err: {error_code} {error_msg}"
                )
                time.sleep(1)
                continue
                
            # Success
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"✅ {side_str} Fill! Ticket: {result.order}, Mode: {filling_mode}")
                
                # Cache the successful filling mode so we don't guess next time
                self._filling_modes[symbol] = filling_mode
                
                # Check for partial fills / true volumes
                actual_price = result.price
                actual_volume = result.volume
                
                # Validate the position actually exists
                time.sleep(0.5)  # Let MT5 server catch up
                position_verified = self._verify_position(result.order, symbol)
                if not position_verified:
                    msg = f"API returned DONE, but position/deal ticket {result.order} not found."
                    self.logger.error(msg)
                    return ExecutionResult(False, error_detail=msg)
                    
                return ExecutionResult(
                    success=True,
                    ticket=result.order,
                    fill_price=actual_price,
                    volume_filled=actual_volume,
                    comment=comment
                )
                
            # Failure handling
            error_code, error_msg = mt5.last_error()
            ret_str = getattr(result, 'comment', 'N/A')
            
            self.logger.warning(
                f"[{attempt+1}/{max_retries}] Rejected (code: {result.retcode}): {ret_str}"
            )
            
            # Explicitly loop onto next filling mode if that's the error
            if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
                self.logger.info(f"Invalid filling mode ({filling_mode}). Retrying...")
                continue
                
            # Auto-blocks: Margin issues, prices changing wildly, quotes off, or AutoTrading Disabled
            if result.retcode in [
                mt5.TRADE_RETCODE_NO_MONEY,
                mt5.TRADE_RETCODE_TRADE_DISABLED,
                mt5.TRADE_RETCODE_MARKET_CLOSED,
                mt5.TRADE_RETCODE_CLIENT_DISABLES_AT  # Code 10027
            ]:
                self.logger.error(f"Execution FATAL: {result.retcode} - {ret_str}")
                break  # Don't exhaust retries for hard blocks
                
            # Sleep before next attempt
            time.sleep(1)
            
        # If we exit the loop without success
        msg = f"Execution failed for {side_str} {symbol} after {max_retries} attempts."
        self.logger.error(msg)
        return ExecutionResult(success=False, error_detail=msg)

    def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float,
        is_buy: bool,
        price: float,
        comment: str = "Close Pos",
        max_retries: int = 3
    ) -> ExecutionResult:
        """
        Close an existing standard position cleanly.
        (Needs to send opposite action to the original order type, mapping 'position'=ticket).
        is_buy here means the ORIGINAL position was a BUY, so we will SEND a SELL to close it.
        """
        order_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        side_str = "SELL (Close)" if is_buy else "BUY (Close)"
        deviation = self.cfg.risk.slippage_points
        magic = self.cfg.trading.magic_number

        self.logger.info(f"Closing Ticket {ticket} -> {side_str} {volume} {symbol} @ {price}")

        if self.cfg.trading.mode != "LIVE":
            return ExecutionResult(
                success=True,
                ticket=ticket,
                fill_price=price,
                volume_filled=volume,
                comment=f"{comment} [DRY]"
            )
            
        for attempt in range(max_retries):
            filling_mode = self._get_filling_mode(symbol, attempt)
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "price": price,
                "deviation": deviation,
                "magic": magic,
                "comment": comment[:27],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            
            result = mt5.order_send(request)
            
            if result is None:
                error_code, error_msg = mt5.last_error()
                self.logger.warning(
                    f"[{attempt+1}/{max_retries}] close order_send None. Err: {error_msg}"
                )
                time.sleep(1)
                continue
                
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"✅ Closed Position {ticket}! New Ticket: {result.order}")
                self._filling_modes[symbol] = filling_mode
                return ExecutionResult(
                    success=True,
                    ticket=result.order,
                    fill_price=result.price,
                    volume_filled=result.volume,
                    comment=comment
                )
                
            ret_str = getattr(result, 'comment', 'N/A')
            if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
                continue
                
            if result.retcode in [mt5.TRADE_RETCODE_NO_MONEY, mt5.TRADE_RETCODE_TRADE_DISABLED, mt5.TRADE_RETCODE_MARKET_CLOSED, mt5.TRADE_RETCODE_CLIENT_DISABLES_AT]:
                self.logger.error(f"Fatal Close err {result.retcode} - {ret_str}")
                break
                
            time.sleep(1)
            
        return ExecutionResult(success=False, error_detail=f"Failed to close {ticket}")
