"""
Download historical OHLCV data from MT5 (5ers/Eightcap account).

Run this ONCE on the machine where MT5 is running:
    python backtest/download_mt5_data.py

Output: backtest/src/data/ohlcv/<SYMBOL>_<TF>_<YEAR>.csv
Format: time,open,high,low,close,volume  (UTC timestamps)

The CSV files are what the backtest simulator reads from data/ohlcv/.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Run: pip install MetaTrader5")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────

SYMBOLS = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD',
    'AUDUSD', 'NZDUSD', 'EURGBP', 'EURJPY', 'EURCHF',
    'EURAUD', 'EURCAD', 'EURNZD', 'GBPJPY', 'GBPCHF',
    'GBPAUD', 'GBPCAD', 'GBPNZD', 'AUDJPY', 'AUDCHF',
    'AUDCAD', 'AUDNZD', 'NZDCHF', 'NZDCAD', 'CADJPY',
    'CADCHF', 'CHFJPY', 'XAUUSD',
]

TIMEFRAMES = {
    'M15': mt5.TIMEFRAME_M15,
    'H1':  mt5.TIMEFRAME_H1,
    'H4':  mt5.TIMEFRAME_H4,
    'D1':  mt5.TIMEFRAME_D1,
    'W1':  mt5.TIMEFRAME_W1,
}

START_DATE = datetime(2010, 1, 1, tzinfo=timezone.utc)
END_DATE   = datetime.now(timezone.utc)

OUTPUT_DIR = Path(__file__).parent / "src" / "data" / "ohlcv"

# ── Main ─────────────────────────────────────────────────────────────────────

def download_symbol_tf(symbol: str, tf_name: str, tf_const: int) -> bool:
    rates = mt5.copy_rates_range(symbol, tf_const, START_DATE, END_DATE)
    if rates is None or len(rates) == 0:
        print(f"  [{symbol} {tf_name}] No data returned (symbol may not exist on this broker)")
        return False

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']].rename(
        columns={'tick_volume': 'volume'}
    )
    df = df.sort_values('time').reset_index(drop=True)

    # Split by year so files stay manageable
    for year, group in df.groupby(df['time'].dt.year):
        fname = OUTPUT_DIR / f"{symbol}_{tf_name}_{year}.csv"
        group.to_csv(fname, index=False)
        print(f"  [{symbol} {tf_name}] {year}: {len(group):,} bars → {fname.name}")

    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not mt5.initialize():
        print(f"MT5 initialize() failed: {mt5.last_error()}")
        print("Make sure MT5 is running and logged in to your 5ers account.")
        sys.exit(1)

    info = mt5.account_info()
    print(f"Connected: {info.name} | Server: {info.server} | Balance: ${info.balance:,.2f}")
    print(f"Downloading {len(SYMBOLS)} symbols × {len(TIMEFRAMES)} timeframes")
    print(f"Range: {START_DATE.date()} → {END_DATE.date()}")
    print(f"Output: {OUTPUT_DIR}\n")

    failed = []
    for symbol in SYMBOLS:
        print(f"→ {symbol}")
        for tf_name, tf_const in TIMEFRAMES.items():
            ok = download_symbol_tf(symbol, tf_name, tf_const)
            if not ok:
                failed.append(f"{symbol}_{tf_name}")

    mt5.shutdown()

    print("\n✅ Done.")
    if failed:
        print(f"⚠️  Skipped (no data): {', '.join(failed)}")
    print(f"\nCSV files written to: {OUTPUT_DIR}")
    print("You can now run the backtest with: python backtest/src/main_live_bot_backtest.py")


if __name__ == "__main__":
    main()
