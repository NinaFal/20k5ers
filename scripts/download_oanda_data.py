#!/usr/bin/env python3
"""
OANDA Historical Data Downloader

Downloads historical OHLCV data from OANDA API for missing symbols.
Supports D1, H4, W1, MN timeframes from 2003-2025.

Usage:
    python scripts/download_oanda_data.py
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import requests
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# OANDA API Configuration (read from environment / .env)
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_API_URL = "https://api-fxpractice.oanda.com"

# Missing symbols to download - 40 forex pairs we don't have yet
# (verified available on OANDA Practice, but not in our data/ohlcv)
MISSING_SYMBOLS = [
    # HKD pairs
    "AUD_HKD", "CAD_HKD", "CHF_HKD", "EUR_HKD", "GBP_HKD", "NZD_HKD", "USD_HKD", "HKD_JPY",
    # SGD pairs
    "AUD_SGD", "CAD_SGD", "EUR_SGD", "GBP_SGD", "NZD_SGD", "USD_SGD", "SGD_CHF", "SGD_JPY",
    # Scandinavian
    "EUR_DKK", "EUR_NOK", "EUR_SEK", "USD_DKK", "USD_NOK", "USD_SEK",
    # Eastern European
    "EUR_CZK", "EUR_HUF", "EUR_PLN", "USD_CZK", "USD_HUF", "USD_PLN", "GBP_PLN",
    # Exotics
    "CHF_ZAR", "EUR_TRY", "EUR_ZAR", "GBP_ZAR", "TRY_JPY", "USD_CNH", 
    "USD_MXN", "USD_THB", "USD_TRY", "USD_ZAR", "ZAR_JPY"
]

# NOT available on OANDA Practice account (only 68 CURRENCY pairs):
# - ADA_USD, XRP_USD, BTC_USD, ETH_USD (crypto) - not on OANDA
# - XAU_USD, XAG_USD (metals) - only on Live account
# - SPX500_USD, NAS100_USD (indices) - only on Live account

# Timeframes to download
TIMEFRAMES = {
    "D": "D1",      # Daily
    "H4": "H4",     # 4-hour
    "W": "W1",      # Weekly
    "M": "MN",      # Monthly
}

# Output directory
OUTPUT_DIR = Path("data/ohlcv")


def download_oanda_candles(
    instrument: str,
    granularity: str,
    from_date: datetime,
    to_date: datetime
) -> pd.DataFrame:
    """
    Download candles from OANDA API.
    
    Args:
        instrument: OANDA instrument (e.g., EUR_USD)
        granularity: OANDA granularity (D, H4, W, M)
        from_date: Start date
        to_date: End date
        
    Returns:
        DataFrame with OHLCV data
    """
    url = f"{OANDA_API_URL}/v3/instruments/{instrument}/candles"
    
    headers = {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Note: OANDA API does NOT allow 'count' when 'from' and 'to' are specified
    params = {
        "granularity": granularity,
        "from": from_date.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "to": to_date.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "price": "M"  # Mid prices
    }
    
    try:
        print(f"  Requesting {instrument} {granularity} from {from_date.date()} to {to_date.date()}...")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if "candles" not in data or len(data["candles"]) == 0:
            print(f"  ⚠️ No candles returned for {instrument}")
            return pd.DataFrame()
        
        # Parse candles
        candles = []
        for candle in data["candles"]:
            if not candle.get("complete", False):
                continue  # Skip incomplete candles
                
            candles.append({
                "time": pd.to_datetime(candle["time"]),
                "open": float(candle["mid"]["o"]),
                "high": float(candle["mid"]["h"]),
                "low": float(candle["mid"]["l"]),
                "close": float(candle["mid"]["c"]),
                "volume": int(candle["volume"])
            })
        
        df = pd.DataFrame(candles)
        print(f"  ✓ Downloaded {len(df)} candles")
        return df
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error downloading {instrument}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return pd.DataFrame()


def download_full_history(
    instrument: str,
    granularity: str,
    start_year: int = 2003,  # OANDA will return data from earliest available
    end_year: int = 2025
) -> pd.DataFrame:
    """
    Download full history by chunking into yearly batches.
    
    Note: OANDA Practice account history varies by pair:
    - Major pairs (EUR_USD, GBP_USD): data from ~2003
    - Cross pairs (CAD_CHF, EUR_AUD): data from ~2005-2008
    - Exotics (USD_CNH, TRY_JPY): may have shorter history
    """
    all_candles = []
    
    # For daily and 4H, chunk by year
    # For weekly/monthly, can do longer periods
    if granularity in ["D", "H4"]:
        chunk_months = 12 if granularity == "D" else 6
    else:
        chunk_months = 60  # 5 years for W/M
    
    current_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    
    while current_date < end_date:
        chunk_end = min(
            current_date + timedelta(days=chunk_months * 30),
            end_date
        )
        
        df_chunk = download_oanda_candles(
            instrument=instrument,
            granularity=granularity,
            from_date=current_date,
            to_date=chunk_end
        )
        
        if not df_chunk.empty:
            all_candles.append(df_chunk)
        
        current_date = chunk_end + timedelta(days=1)
        time.sleep(0.5)  # Rate limiting
    
    if not all_candles:
        return pd.DataFrame()
    
    # Combine all chunks
    df = pd.concat(all_candles, ignore_index=True)
    
    # Remove duplicates and sort
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    
    return df


def save_to_csv(df: pd.DataFrame, symbol: str, timeframe: str):
    """Save DataFrame to CSV in standard format."""
    if df.empty:
        print(f"  ⚠️ No data to save for {symbol}_{timeframe}")
        return
    
    # Create output directory if needed
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Filename format: SYMBOL_TF_2003_2025.csv (consistent with existing data)
    filename = OUTPUT_DIR / f"{symbol}_{timeframe}_2003_2025.csv"
    
    # Save with standard columns
    df_out = df.copy()
    df_out = df_out.rename(columns={"time": "timestamp"})
    df_out = df_out[["timestamp", "open", "high", "low", "close", "volume"]]
    
    df_out.to_csv(filename, index=False)
    print(f"  ✓ Saved to {filename} ({len(df_out)} candles)")


def main():
    """Main download loop."""
    print("=" * 80)
    print("OANDA Historical Data Downloader")
    print("=" * 80)
    print(f"Downloading {len(MISSING_SYMBOLS)} symbols × {len(TIMEFRAMES)} timeframes")
    print(f"Period: 2003-2025 (OANDA will return from earliest available)")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 80)
    print()
    
    total_symbols = len(MISSING_SYMBOLS)
    total_tfs = len(TIMEFRAMES)
    completed = 0
    failed = []
    
    for idx, symbol in enumerate(MISSING_SYMBOLS, 1):
        print(f"\n[{idx}/{total_symbols}] Processing {symbol}...")
        
        for granularity, tf_name in TIMEFRAMES.items():
            print(f"  Timeframe: {tf_name} ({granularity})")
            
            try:
                df = download_full_history(
                    instrument=symbol,
                    granularity=granularity,
                    start_year=2003,  # OANDA returns from earliest available
                    end_year=2025
                )
                
                if not df.empty:
                    save_to_csv(df, symbol, tf_name)
                    completed += 1
                else:
                    print(f"  ❌ No data available for {symbol}_{tf_name}")
                    failed.append(f"{symbol}_{tf_name}")
                    
            except Exception as e:
                print(f"  ❌ Failed to download {symbol}_{tf_name}: {e}")
                failed.append(f"{symbol}_{tf_name}")
            
            time.sleep(0.3)  # Rate limiting between timeframes
        
        time.sleep(1)  # Rate limiting between symbols
    
    # Summary
    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"✓ Successfully downloaded: {completed}/{total_symbols * total_tfs} files")
    
    if failed:
        print(f"❌ Failed: {len(failed)} files")
        print("\nFailed downloads:")
        for item in failed:
            print(f"  - {item}")
    else:
        print("✓ All downloads successful!")
    
    print("=" * 80)


if __name__ == "__main__":
    main()
