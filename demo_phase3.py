"""
Demo script to purely test Phase 3 Data Fetcher Features cleanly.
Run explicitly with: .venv\Scripts\python demo_phase3.py
"""

from src.config import load_config
from src.data_fetcher import MT5DataFetcher
import MetaTrader5 as mt5
import sys

def demo_phase3():
    # 1. Load config
    cfg = load_config()
    
    print("\n" + "="*50)
    print("Testing Phase 3 Data Fetching Features (EURUSD)...")
    print("="*50)
    
    # 2. Quiet connection (no logger spam)
    if not mt5.initialize(login=cfg.mt5.login, password=cfg.mt5.password, server=cfg.mt5.server):
        print("❌ MT5 Init Failed", mt5.last_error())
        sys.exit(1)

    fetcher = MT5DataFetcher(cfg=cfg, logger=None)
    
    try:
        # A. Fetch Symbol Properties
        info = fetcher.get_symbol_info("USDJPY")
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
        mt5.shutdown()

if __name__ == "__main__":
    demo_phase3()
