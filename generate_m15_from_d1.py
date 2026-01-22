#!/usr/bin/env python3
"""
Generate M15 (15-minute) data from existing D1 (daily) data.
Synthetic resample: D1 candles → M15 candles using forward-fill + random intraday variation.

This is useful for backtesting at intraday levels without needing OANDA API.
"""

import logging
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

DATA_DIR = Path("data/ohlcv")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# Generate M15 from D1 using realistic intraday variation
# ═══════════════════════════════════════════════════════════════════════

def generate_m15_from_d1(d1_file: Path, m15_file: Path) -> bool:
    """
    Read D1 OHLCV data and generate synthetic M15 candles.
    
    Strategy:
    - Each D1 candle = 96 M15 candles (24 hours * 4 quarters)
    - Use D1 O/H/L/C to guide realistic intraday movement
    - Generate 4 M15 values within each D1 candle
    """
    
    try:
        # Load D1 data
        df_d1 = pd.read_csv(d1_file)
        df_d1["time"] = pd.to_datetime(df_d1["time"])
        
        if len(df_d1) < 10:
            log.warning(f"  ⚠ {d1_file.name}: Only {len(df_d1)} D1 candles")
            return False
        
        log.info(f"  Loaded {len(df_d1)} D1 candles")
        
        # Generate M15 candles
        m15_rows = []
        
        for idx, row in df_d1.iterrows():
            d1_time = pd.Timestamp(row["time"])
            d1_open = float(row["Open"])
            d1_close = float(row["Close"])
            d1_high = float(row["High"])
            d1_low = float(row["Low"])
            d1_range = d1_high - d1_low
            
            # Generate 96 M15 candles for this D1 candle
            # Start at market open (00:00 or from previous close)
            m15_start_time = d1_time
            
            # Realistic intraday path: Open -> vary -> tend towards Close
            price_path = [d1_open]
            
            for i in range(1, 96):
                # Progress through the day (0 to 1)
                progress = i / 96
                
                # Weighted movement: start near open, end near close
                target_price = d1_open + (d1_close - d1_open) * progress
                
                # Add random walk within the day's range
                random_move = np.random.normal(0, d1_range * 0.05)
                next_price = target_price + random_move
                
                # Keep within day's high/low ± some margin
                next_price = max(d1_low * 0.98, min(d1_high * 1.02, next_price))
                price_path.append(next_price)
            
            # Generate M15 OHLCV from price path
            for q in range(96):
                m15_time = m15_start_time + timedelta(minutes=15 * q)
                
                if q < len(price_path) - 1:
                    m15_open = price_path[q]
                    m15_close = price_path[q + 1]
                    m15_high = max(m15_open, m15_close) + abs(np.random.normal(0, d1_range * 0.02))
                    m15_low = min(m15_open, m15_close) - abs(np.random.normal(0, d1_range * 0.02))
                else:
                    m15_open = price_path[-1]
                    m15_close = d1_close  # Ensure last M15 closes at D1 close
                    m15_high = max(m15_open, m15_close)
                    m15_low = min(m15_open, m15_close)
                
                # Keep High >= Low
                if m15_high < m15_low:
                    m15_high, m15_low = m15_low, m15_high
                
                m15_rows.append({
                    "time": m15_time,
                    "Open": m15_open,
                    "High": m15_high,
                    "Low": m15_low,
                    "Close": m15_close,
                    "Volume": 0,
                })
        
        # Create DataFrame
        df_m15 = pd.DataFrame(m15_rows)
        df_m15["time"] = pd.to_datetime(df_m15["time"])
        df_m15 = df_m15.sort_values("time").reset_index(drop=True)
        
        # Save
        df_m15.to_csv(
            m15_file,
            index=False,
            float_format="%.8f"
        )
        
        log.info(f"  ✓ Generated {len(df_m15)} M15 candles → {m15_file.name}")
        return True
    
    except Exception as e:
        log.error(f"  ✗ Error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    log.info("="*80)
    log.info("GENERATING M15 DATA FROM D1 (SYNTHETIC INTRADAY)")
    log.info("="*80)
    log.info(f"Source: {DATA_DIR}/*_D1_2003_2025.csv")
    log.info(f"Output: {DATA_DIR}/*_M15_2020_2025.csv")
    log.info("")
    
    # Find all D1 files
    d1_files = sorted(DATA_DIR.glob("*_D1_2003_2025.csv"))
    
    if not d1_files:
        log.error("No D1 files found!")
        return
    
    log.info(f"Found {len(d1_files)} D1 files\n")
    
    results = {"success": [], "failed": []}
    
    for i, d1_file in enumerate(d1_files, 1):
        # Extract symbol
        symbol = d1_file.name.replace("_D1_2003_2025.csv", "")
        
        log.info(f"[{i}/{len(d1_files)}] {symbol}")
        log.info("-" * 60)
        
        # Output file (only 2020-2025, not 2003)
        m15_file = DATA_DIR / f"{symbol}_M15_2020_2025.csv"
        
        # Generate
        success = generate_m15_from_d1(d1_file, m15_file)
        
        if success:
            results["success"].append(symbol)
        else:
            results["failed"].append(symbol)
        
        log.info("")
    
    # Summary
    log.info("="*80)
    log.info("SUMMARY")
    log.info("="*80)
    log.info(f"✅ Success: {len(results['success'])}/{len(d1_files)} symbols")
    if results["failed"]:
        log.info(f"✗ Failed:  {len(results['failed'])} symbols ({', '.join(results['failed'])})")
    log.info("="*80)
    log.info("\nNext: Test backtest with M15 timeframe")
    log.info("  python scripts/backtest_main_live_bot.py --timeframe M15")


if __name__ == "__main__":
    main()
