#!/usr/bin/env python3
"""
Download ONLY the missing M15 data (5 symbols):
- BTC_USD, ETH_USD (via Binance)
- SPX500_USD, NAS100_USD, UK100_USD (via Yahoo daily->15m)

No registration needed. All free public APIs.
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from io import BytesIO
from dotenv import load_dotenv

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    os.system("pip install -q yfinance")
    import yfinance as yf

# Setup logging
LOG_FILE = Path("logs/m15_download_missing.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Clear previous log
if LOG_FILE.exists():
    LOG_FILE.unlink()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path("data/ohlcv")
DATA_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = datetime(2023, 1, 1)
END_DATE = datetime(2025, 12, 31)

# Missing symbols only
SYMBOLS = {
    "BTC_USD": "BTC-USD",
    "ETH_USD": "ETH-USD",
    "SPX500_USD": "^GSPC",
    "NAS100_USD": "^NDX",
    "UK100_USD": "^FTSE",
}


# ═══════════════════════════════════════════════════════════════════════
# BINANCE API DATA DOWNLOAD (for Crypto)
# ═══════════════════════════════════════════════════════════════════════

def download_from_binance(symbol: str) -> Optional[pd.DataFrame]:
    """
    Download crypto data from Binance API (no authentication required).
    Downloads 1h data and resamples to 15m.
    """
    try:
        if "BTC" in symbol:
            binance_symbol = "BTCUSDT"
        elif "ETH" in symbol:
            binance_symbol = "ETHUSDT"
        else:
            return None
        
        log.info(f"  → Binance ({binance_symbol}, 1h→15m)...")
        url = "https://api.binance.com/api/v3/klines"
        dfs = []
        current_date = START_DATE
        
        while current_date < END_DATE:
            chunk_end = min(current_date + timedelta(days=90), END_DATE)
            params = {
                "symbol": binance_symbol,
                "interval": "1h",
                "startTime": int(current_date.timestamp() * 1000),
                "endTime": int(chunk_end.timestamp() * 1000),
                "limit": 1000,
            }
            try:
                response = requests.get(url, params=params, timeout=30)
                if response.status_code != 200:
                    log.warning(f"    Binance API error: {response.status_code}")
                    break
                
                klines = response.json()
                if not klines:
                    break
                
                rows = []
                for kline in klines:
                    rows.append({
                        "time": pd.to_datetime(kline[0], unit="ms"),
                        "Open": float(kline[1]),
                        "High": float(kline[2]),
                        "Low": float(kline[3]),
                        "Close": float(kline[4]),
                        "Volume": float(kline[7]),
                    })
                
                if rows:
                    dfs.append(pd.DataFrame(rows))
                    log.debug(f"    Chunk {current_date.date()}-{chunk_end.date()}: {len(rows)} candles")
                
            except Exception as e:
                log.debug(f"    Chunk error: {str(e)[:50]}")
                break
            
            current_date = chunk_end
        
        if not dfs:
            log.warning("  ✗ Binance: No data")
            return None
        
        df = pd.concat(dfs, ignore_index=True)
        df["time"] = pd.to_datetime(df["time"])
        df = df.drop_duplicates(subset=["time"], keep="last")
        df = df.sort_values("time").reset_index(drop=True)
        
        # Resample 1h to 15m
        df_15m = df.set_index("time").resample("15min").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).reset_index()
        df_15m = df_15m.dropna(subset=["Close"])
        
        log.info(f"  ✓ Binance: {len(df_15m)} candles (1h→15m)")
        return df_15m
    except Exception as e:
        log.error(f"  ✗ Binance error: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════════════
# YAHOO FINANCE DATA DOWNLOAD (for Indices)
# ═══════════════════════════════════════════════════════════════════════

def download_from_yahoo(symbol: str, yahoo_symbol: str) -> Optional[pd.DataFrame]:
    """
    Download from Yahoo Finance (daily data resampled to 15m).
    """
    try:
        log.info(f"  → Yahoo ({yahoo_symbol}, daily→15m)...")
        df_daily = yf.download(
            yahoo_symbol,
            start=START_DATE.date(),
            end=END_DATE.date(),
            interval="1d",
            progress=False,
            timeout=30,
        )
        
        if df_daily.empty:
            log.warning("  ✗ Yahoo: No daily data")
            return None
        
        df_daily = df_daily.reset_index()
        
        # Handle MultiIndex columns from yfinance
        if isinstance(df_daily.columns, pd.MultiIndex):
            df_daily.columns = [col[0] if col[0] != 'Date' else 'Date' for col in df_daily.columns]
        
        # Normalize column names
        df_daily.columns = [c.lower() for c in df_daily.columns]
        
        if "date" not in df_daily.columns:
            for col in df_daily.columns:
                if "date" in col.lower():
                    df_daily.rename(columns={col: "time"}, inplace=True)
                    break
        else:
            df_daily.rename(columns={"date": "time"}, inplace=True)
        
        df_daily["time"] = pd.to_datetime(df_daily["time"])
        
        # Standardize OHLCV column names
        col_map = {
            "open": "Open",
            "high": "High", 
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        }
        for old, new in col_map.items():
            if old in df_daily.columns:
                df_daily[new] = df_daily[old]
        
        df_daily = df_daily[["time", "Open", "High", "Low", "Close", "Volume"]]
        df_daily = df_daily.dropna(subset=["Close"])
        
        log.debug(f"    Downloaded {len(df_daily)} daily candles")
        
        # Resample daily to 15m
        df_daily = df_daily.set_index("time")
        df_15m = df_daily.resample("15min").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).reset_index()
        df_15m = df_15m.dropna(subset=["Close"])
        
        log.info(f"  ✓ Yahoo: {len(df_15m)} candles (daily→15m)")
        return df_15m
    except Exception as e:
        log.error(f"  ✗ Yahoo error: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════════════
# SAVE DATA
# ═══════════════════════════════════════════════════════════════════════

def save_data(df: pd.DataFrame, symbol: str) -> Path:
    """Save DataFrame to CSV."""
    filename = DATA_DIR / f"{symbol}_M15_2020_2025.csv"
    
    cols = ["time", "Open", "High", "Low", "Close", "Volume"]
    df = df[cols]
    df.to_csv(filename, index=False, float_format="%.8f")
    
    log.info(f"✓ Saved: {filename.name}")
    return filename


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 80)
    log.info("DOWNLOADING MISSING 15-MINUTE DATA (5 symbols)")
    log.info("=" * 80)
    log.info(f"Symbols: {', '.join(SYMBOLS.keys())}")
    log.info(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    log.info("Sources: Binance (BTC/ETH), Yahoo (SPX/NDX/FTSE daily→15m)")
    log.info("=" * 80)
    log.info("")
    
    results = {
        "success": [],
        "partial": [],
        "failed": [],
    }
    
    for i, (symbol, yahoo_sym) in enumerate(SYMBOLS.items(), 1):
        log.info(f"\n[{i}/{len(SYMBOLS)}] {symbol}")
        log.info("-" * 60)
        
        df = None
        source = None
        
        # Try Binance for crypto
        if "BTC" in symbol or "ETH" in symbol:
            df = download_from_binance(symbol)
            if df is not None and len(df) > 100:
                source = "Binance"
        
        # Use Yahoo for indices
        if df is None or len(df) < 100:
            df = download_from_yahoo(symbol, yahoo_sym)
            if df is not None and len(df) > 100:
                source = "Yahoo"
        
        # Save if successful
        if df is not None and len(df) > 0:
            try:
                save_data(df, symbol)
                
                if len(df) > 1000:
                    results["success"].append((symbol, source, len(df)))
                    log.info(f"✅ SUCCESS: {symbol} ({source}, {len(df)} candles)")
                else:
                    results["partial"].append((symbol, source, len(df)))
                    log.warning(f"⚠ PARTIAL: {symbol} ({source}, {len(df)} candles only)")
            except Exception as e:
                results["failed"].append((symbol, str(e)))
                log.error(f"✗ SAVE ERROR: {symbol} - {e}")
        else:
            results["failed"].append((symbol, "No data"))
            log.error(f"✗ FAILED: {symbol} - No data downloaded")
    
    # Summary
    log.info("\n" + "=" * 80)
    log.info("SUMMARY")
    log.info("=" * 80)
    
    total_success = len(results["success"]) + len(results["partial"])
    log.info(f"✅ Total: {total_success}/{len(SYMBOLS)} symbols")
    
    if results["success"]:
        log.info(f"\n   SUCCESS ({len(results['success'])}):")
        for sym, src, cnt in results["success"]:
            log.info(f"   • {sym}: {cnt} candles ({src})")
    
    if results["partial"]:
        log.info(f"\n   PARTIAL ({len(results['partial'])}):")
        for sym, src, cnt in results["partial"]:
            log.info(f"   • {sym}: {cnt} candles ({src})")
    
    if results["failed"]:
        log.info(f"\n   FAILED ({len(results['failed'])}):")
        for sym, err in results["failed"]:
            log.info(f"   • {sym}: {err}")
    
    log.info("=" * 80)
    log.info(f"\n✓ Log saved to: {LOG_FILE}")


if __name__ == "__main__":
    main()
