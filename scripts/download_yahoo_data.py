#!/usr/bin/env python3
"""
Download historical OHLCV data from Yahoo Finance for assets not available on OANDA Practice.
- Metals: Gold (XAU), Silver (XAG)
- Indices: S&P 500, Nasdaq 100
- Crypto: Bitcoin, Ethereum

Yahoo Finance is FREE and requires no API key.
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system(f"{sys.executable} -m pip install yfinance")
    import yfinance as yf

# Output directory
DATA_DIR = Path(__file__).parent.parent / "data" / "ohlcv"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Yahoo Finance tickers mapped to our naming convention
# Format: {our_symbol: (yahoo_ticker, start_year, description)}
YAHOO_SYMBOLS = {
    # Metals - using futures for better historical data
    "XAUUSD": ("GC=F", 2005, "Gold Futures"),
    "XAGUSD": ("SI=F", 2005, "Silver Futures"),
    
    # Indices - using futures for 24h trading alignment with forex
    "SPX500USD": ("ES=F", 2005, "S&P 500 E-mini Futures"),
    "NAS100USD": ("NQ=F", 2005, "Nasdaq 100 E-mini Futures"),
    
    # Crypto
    "BTCUSD": ("BTC-USD", 2014, "Bitcoin USD"),  # BTC data starts ~2014 on Yahoo
    "ETHUSD": ("ETH-USD", 2017, "Ethereum USD"),  # ETH data starts ~2017 on Yahoo
}

# Timeframe mapping: our_tf -> (yfinance_interval, yfinance_period_or_date)
# Note: Yahoo Finance has limitations:
# - 1d, 1wk, 1mo: full history available
# - 1h, 4h: only last 730 days
TIMEFRAMES = {
    "D1": "1d",
    "W1": "1wk",
    "MN": "1mo",
    # H4 not directly available, we'd need to resample from 1h (limited history)
}


def download_symbol(symbol: str, yahoo_ticker: str, start_year: int, timeframe: str) -> bool:
    """Download data for a single symbol/timeframe combination."""
    
    yf_interval = TIMEFRAMES.get(timeframe)
    if not yf_interval:
        print(f"  ⚠️ Timeframe {timeframe} not supported by Yahoo Finance")
        return False
    
    filename = f"{symbol}_{timeframe}_2003_2025.csv"
    filepath = DATA_DIR / filename
    
    # Skip if file exists and has recent data
    if filepath.exists():
        try:
            existing = pd.read_csv(filepath)
            if len(existing) > 100:
                last_date = pd.to_datetime(existing['time'].iloc[-1])
                if last_date > datetime(2024, 12, 1):
                    print(f"  ⏭️ {filename} already up to date ({len(existing)} rows)")
                    return True
        except Exception:
            pass
    
    try:
        print(f"  📥 Downloading {symbol} {timeframe} from {start_year}...")
        
        # Create ticker
        ticker = yf.Ticker(yahoo_ticker)
        
        # Download data
        start_date = f"{start_year}-01-01"
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        df = ticker.history(
            start=start_date,
            end=end_date,
            interval=yf_interval,
            auto_adjust=True,  # Adjust for splits/dividends
        )
        
        if df.empty:
            print(f"  ❌ No data returned for {symbol}")
            return False
        
        # Rename columns to match our format
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "time",
            "Datetime": "time",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        
        # Select and order columns
        columns = ["time", "open", "high", "low", "close", "volume"]
        df = df[[c for c in columns if c in df.columns]]
        
        # Format time column
        df["time"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Remove timezone info if present
        df["time"] = df["time"].str.replace(r"\+.*", "", regex=True)
        
        # Save to CSV
        df.to_csv(filepath, index=False)
        
        print(f"  ✅ Saved {filename}: {len(df)} rows ({df['time'].iloc[0]} to {df['time'].iloc[-1]})")
        return True
        
    except Exception as e:
        print(f"  ❌ Error downloading {symbol}: {e}")
        return False


def create_h4_from_hourly(symbol: str, yahoo_ticker: str) -> bool:
    """
    Try to create H4 data from hourly data.
    Note: Yahoo Finance only provides ~730 days of hourly data.
    """
    filename = f"{symbol}_H4_2003_2025.csv"
    filepath = DATA_DIR / filename
    
    try:
        print(f"  📥 Downloading {symbol} 1h for H4 resampling...")
        
        ticker = yf.Ticker(yahoo_ticker)
        
        # Download max available hourly data (last 730 days)
        df = ticker.history(period="730d", interval="1h", auto_adjust=True)
        
        if df.empty or len(df) < 100:
            print(f"  ⚠️ Insufficient hourly data for {symbol} H4")
            return False
        
        # Resample to 4H
        df_h4 = df.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna()
        
        # Rename columns
        df_h4 = df_h4.reset_index()
        df_h4 = df_h4.rename(columns={
            "Datetime": "time",
            "Date": "time",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        
        # Format time
        df_h4["time"] = pd.to_datetime(df_h4["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Save
        df_h4.to_csv(filepath, index=False)
        
        print(f"  ✅ Saved {filename}: {len(df_h4)} rows (H4 from hourly, ~2 years)")
        return True
        
    except Exception as e:
        print(f"  ⚠️ Could not create H4 for {symbol}: {e}")
        return False


def main():
    print("=" * 60)
    print("Yahoo Finance Data Downloader")
    print("Assets: Gold, Silver, S&P 500, Nasdaq 100, Bitcoin, Ethereum")
    print("=" * 60)
    
    success_count = 0
    fail_count = 0
    
    for symbol, (yahoo_ticker, start_year, desc) in YAHOO_SYMBOLS.items():
        print(f"\n[{symbol}] {desc} ({yahoo_ticker})")
        
        # Download D1, W1, MN
        for tf in ["D1", "W1", "MN"]:
            if download_symbol(symbol, yahoo_ticker, start_year, tf):
                success_count += 1
            else:
                fail_count += 1
            time.sleep(0.5)  # Be nice to Yahoo
        
        # Try to get H4 data (limited to ~2 years)
        if create_h4_from_hourly(symbol, yahoo_ticker):
            success_count += 1
        else:
            fail_count += 1
        
        time.sleep(1)  # Rate limiting between symbols
    
    print("\n" + "=" * 60)
    print(f"DOWNLOAD COMPLETE")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {fail_count}")
    print("=" * 60)
    
    # List created files
    print("\nCreated files:")
    for symbol in YAHOO_SYMBOLS.keys():
        for tf in ["D1", "H4", "W1", "MN"]:
            filepath = DATA_DIR / f"{symbol}_{tf}_2003_2025.csv"
            if filepath.exists():
                size = filepath.stat().st_size / 1024
                print(f"  ✅ {filepath.name} ({size:.1f} KB)")
            else:
                print(f"  ❌ {filepath.name} (missing)")


if __name__ == "__main__":
    main()
