"""
Quick script to test MT5 Connection & Data Fetching.
Run this from your terminal: .venv\Scripts\python test_mt5_connection.py
"""

from src.config import load_config
from src.logger import setup_logger
from src.mt5_connector import MT5Connector
from src.data_fetcher import MT5DataFetcher
import sys

def test_connection():
    # 1. Load config and setup logger
    cfg = load_config()
    setup_logger(cfg.logging)
    
    print("\n" + "="*40)
    print("Testing MT5 Connection...")
    print("="*40)
    
    # 2. Test Connection
    conn = MT5Connector(cfg)
    try:
        acct = conn.connect()
        print("\n✅ CONNECTION SUCCESSFUL!")
        print(f"Login  : {acct.login}")
        print(f"Server : {acct.server}")
        print(f"Balance: {acct.balance:,.2f} {acct.currency}")
        print(f"Mode   : {acct.margin_mode} (Hedging={acct.is_hedging})")
    except Exception as e:
        print("\n❌ CONNECTION FAILED:", e)
        sys.exit(1)

    # 3. Test Data fetcher (Phase 3 properties)
    print("\n" + "="*40)
    print("Testing Phase 3 Data Fetching (EURUSD)...")
    print("="*40)
    fetcher = MT5DataFetcher(cfg)
    
    try:
        # A. Fetch Symbol Properties
        info = fetcher.get_symbol_info("EURUSD")
        print("\n✅ SYMBOL PROPERTIES:")
        print(f"  Digits       : {info.digits}")
        print(f"  Spread (raw) : {info.spread}")
        print(f"  Contract Size: {info.contract_size}")
        print(f"  Point Size   : {info.point}")
        print(f"  Min Volume   : {info.volume_min}")
        print(f"  Stops Level  : {info.trade_stops_level} points")
        print(f"  Freeze Level : {info.trade_freeze_level} points")

        # B. Fetch current tick (Phase 3: dynamic spread & stale check)
        tick = fetcher.get_current_tick("EURUSD")
        print("\n✅ LIVE TICK (Stale Guard: OK!):")
        print(f"  Bid          : {tick['bid']}")
        print(f"  Ask          : {tick['ask']}")
        print(f"  Spread Points: {tick['spread_points']:.1f}")
        print(f"  Volume       : {tick['volume']}")

        # C. Fetch candles
        df = fetcher.get_candles("EURUSD", "M15", count=3)
        print(f"\n✅ OHLCV CANDLES ({len(df)} fetched):")
        print(df[['time', 'open', 'high', 'low', 'close']])
        
    except Exception as e:
        print("\n❌ DATA FETCH FAILED:", e)
    
    finally:
        conn.disconnect()

if __name__ == "__main__":
    test_connection()
