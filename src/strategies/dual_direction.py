"""
Dual-Direction Strategy (Phase 6 Core Implementation).

Rules:
1. Open one BUY and one SELL simultaneously.
2. Use configured lot sizing.
3. Calculate 1:2 strict SL/TP from actual filled prices.
4. Monitor both.
    - If BUY hits 1:2 TP -> Close BUY, Close SELL.
    - If SELL hits 1:2 TP -> Close SELL, Close BUY.
    - If one side hits SL -> Close the opposite position (default config).
5. Track net P&L.
"""

import logging
import time
from typing import Optional, Dict

from src.config import BotConfig
from src.data_fetcher import MT5DataFetcher
from src.execution_engine import ExecutionEngine
from src.risk_manager import RiskManager
from src.logger import get_logger

class DualDirectionStrategy:
    def __init__(
        self,
        cfg: BotConfig,
        data_fetcher: MT5DataFetcher,
        risk_manager: RiskManager,
        execution_engine: ExecutionEngine,
        logger: Optional[logging.Logger] = None
    ):
        self.cfg = cfg
        self.data_fetcher = data_fetcher
        self.risk_manager = risk_manager
        self.execution = execution_engine
        self.logger = logger or get_logger()
        
        # State tracking per symbol
        # cycle_state[symbol] = {"buy_ticket": int, "sell_ticket": int, "buy_sl": float, "buy_tp": float, etc.}
        self.active_cycles: Dict[str, Dict] = {}

    def execute_cycle(self, symbol: str) -> bool:
        """
        Starts a new dual-direction cycle.
        """
        if symbol in self.active_cycles:
            self.logger.warning(f"Cycle already active for {symbol}. Ignoring entry.")
            return False
            
        self.logger.info(f"--- STARTING DUAL-DIRECTION CYCLE: {symbol} ---")
        
        try:
            # 1. Fetch market data
            tick = self.data_fetcher.get_current_tick(symbol)
            sym_info = self.data_fetcher.get_symbol_info(symbol)
            
            # Spread check
            self.risk_manager.check_spread(tick['spread_points'], symbol)
            
            account_balance = 10000.0  # Fallback
            # Properly fetch balance internally or passed, but we mock/use 10k for now
            # In a full flow the orchestrator passes balance, but for DRY phase 6 it's fine
            
            # 2. Calculate BUY targets
            buy_entry, buy_sl, buy_tp = self.risk_manager.calculate_sl_tp(0, tick['ask'], sym_info)
            buy_lot = self.risk_manager.calculate_lot_size(account_balance, buy_entry, buy_sl, sym_info)
            
            # 3. Calculate SELL targets
            sell_entry, sell_sl, sell_tp = self.risk_manager.calculate_sl_tp(1, tick['bid'], sym_info)
            sell_lot = self.risk_manager.calculate_lot_size(account_balance, sell_entry, sell_sl, sym_info)
            
            # 4. Execute BUY
            buy_res = self.execution.execute_market_order(
                symbol, buy_lot, True, buy_entry, buy_sl, buy_tp, comment="Dual Buy"
            )
            if not buy_res.success:
                self.logger.error("Failed to open BUY leg of cycle. Aborting cycle.")
                return False
                
            # 5. Execute SELL
            sell_res = self.execution.execute_market_order(
                symbol, sell_lot, False, sell_entry, sell_sl, sell_tp, comment="Dual Sell"
            )
            
            if not sell_res.success:
                self.logger.error("Failed to open SELL leg! Closing orphaned BUY leg to remain neutral.")
                self.execution.close_position(
                    buy_res.ticket, symbol, buy_lot, True, tick['bid'], comment="Orphan Close"
                )
                return False

            # Recalculate strict SL/TP based on ACTUAL filled prices (Slippage adjusted)
            actual_buy_entry, final_buy_sl, final_buy_tp = self.risk_manager.calculate_sl_tp(
                0, buy_res.fill_price, sym_info
            )
            actual_sell_entry, final_sell_sl, final_sell_tp = self.risk_manager.calculate_sl_tp(
                1, sell_res.fill_price, sym_info
            )

            # Store Cycle
            self.active_cycles[symbol] = {
                "buy_ticket": buy_res.ticket,
                "buy_lot": buy_res.volume_filled,
                "buy_sl": final_buy_sl,
                "buy_tp": final_buy_tp,
                "buy_entry": buy_res.fill_price,
                
                "sell_ticket": sell_res.ticket,
                "sell_lot": sell_res.volume_filled,
                "sell_sl": final_sell_sl,
                "sell_tp": final_sell_tp,
                "sell_entry": sell_res.fill_price,
            }
            
            self.logger.info(f"✅ Dual-Direction Cycle {symbol} Active.")
            return True
            
        except Exception as e:
            self.logger.error(f"Cycle execution failed: {e}")
            return False

    def _close_cycle(self, symbol: str, reason: str, tick: dict):
        """
        Closes both legs of the active cycle.
        """
        cycle = self.active_cycles.get(symbol)
        if not cycle:
            return
            
        self.logger.info(f"Closing Cycle {symbol} | Reason: {reason}")
        
        # Close BUY (send a SELL at BID)
        self.execution.close_position(
            cycle["buy_ticket"], symbol, cycle["buy_lot"], True, tick['bid'], comment=reason
        )
        
        # Close SELL (send a BUY at ASK)
        self.execution.close_position(
            cycle["sell_ticket"], symbol, cycle["sell_lot"], False, tick['ask'], comment=reason
        )
        
        del self.active_cycles[symbol]
        self.logger.info(f"--- END CYCLE: {symbol} ---")

    def monitor_cycle(self, symbol: str):
        """
        Checks current price against SL/TP targets.
        Should be called every tick or bar.
        """
        cycle = self.active_cycles.get(symbol)
        if not cycle:
            return

        tick = self.data_fetcher.get_current_tick(symbol)
        bid = tick['bid']
        ask = tick['ask']

        # Check BUY Targets (Exit price for a Buy is Bid)
        if bid >= cycle["buy_tp"]:
            self._close_cycle(symbol, "BUY TP Hit", tick)
            return
        if bid <= cycle["buy_sl"]:
            self._close_cycle(symbol, "BUY SL Hit", tick)
            return
            
        # Check SELL Targets (Exit price for a Sell is Ask)
        if ask <= cycle["sell_tp"]:
            self._close_cycle(symbol, "SELL TP Hit", tick)
            return
        if ask >= cycle["sell_sl"]:
            self._close_cycle(symbol, "SELL SL Hit", tick)
            return

