"""
Demo Script combining Phases 2, 3, 4, and 5.
Proves the connection, data fetching, risk calculation, and order execution layers work together!
"""

from src.config import load_config
from src.logger import setup_logger
from src.mt5_connector import MT5Connector
from src.data_fetcher import MT5DataFetcher
from src.risk_manager import RiskManager
from src.execution_engine import ExecutionEngine
import sys

def run_integration_test():
    # -------------------------------------------------------------
    # PHASE 1: Config & Logger Foundation
    # -------------------------------------------------------------
    cfg = load_config()
    cfg.logging.level = "WARNING" # Keep console clean
    setup_logger(cfg.logging)
    
    # -------------------------------------------------------------
    # PHASE 2: Connection
    # -------------------------------------------------------------
    print("\n" + "="*50)
    print("🚀 RUNNING PHASE 2 -> 5 INTEGRATION TEST 🚀")
    print("="*50)
    
    conn = MT5Connector(cfg)
    try:
        acct = conn.connect()
        print(f"✅ PHASE 2 (CONNECTION)        : Connected to {acct.server}. Bal: ${acct.balance:.2f}")
    except Exception as e:
        print(f"❌ PHASE 2 (CONNECTION) FAILED : {e}")
        sys.exit(1)

    try:
        # -------------------------------------------------------------
        # PHASE 3: Market Data Layer
        # -------------------------------------------------------------
        symbol = cfg.trading.symbols[0]
        data_fetcher = MT5DataFetcher(cfg, logger=None)
        
        tick = data_fetcher.get_current_tick(symbol)
        sym_info = data_fetcher.get_symbol_info(symbol)
        print(f"✅ PHASE 3 (DATA FETCHER)      : {symbol} Bid: {tick['bid']:.5f} | Spread: {tick['spread_points']} pts")

        # -------------------------------------------------------------
        # PHASE 4: Risk & Price Calculation
        # -------------------------------------------------------------
        risk_manager = RiskManager(cfg, logger=None)
        
        # Calculate exactly where entry & exit should be (Using a BUY)
        # Entry = Current Ask
        entry_price, sl_price, tp_price = risk_manager.calculate_sl_tp(
            order_type=0,  # BUY
            entry_price=tick['ask'],
            sym_info=sym_info
        )
        
        # Calculate maximum safe volume for a 1% risk given that Entry/SL distance
        volume = risk_manager.calculate_lot_size(
            account_balance=acct.balance,
            entry_price=entry_price,
            sl_price=sl_price,
            sym_info=sym_info
        )
        print(f"✅ PHASE 4 (RISK MANAGER)      : Risk=1%. Calc Vol: {volume} Lots (Min:{sym_info.volume_min})")
        print(f"                                 Entry: {entry_price:.5f} -> SL: {sl_price:.5f} -> TP: {tp_price:.5f}")

        # -------------------------------------------------------------
        # PHASE 5: Safe Execution Engine
        # -------------------------------------------------------------
        exec_engine = ExecutionEngine(cfg, logger=None)
        
        print(f"✅ PHASE 5 (EXECUTION ENGINE)  : Sending mock order to Execution Engine...")
        result = exec_engine.execute_market_order(
            symbol=symbol,
            volume=volume,
            is_buy=True,
            price=entry_price,
            sl=sl_price,
            tp=tp_price,
            comment="Integration Demo"
        )
        
        if result.success:
            print(f"🏆 SUCCESS! Trade '{result.comment}' simulated safely.")
        else:
            print(f"❌ EXECUTION FAILED: {result.error_detail}")

    finally:
        conn.disconnect()
        print("="*50 + "\n")

if __name__ == "__main__":
    run_integration_test()
