#!/usr/bin/env python3
"""
Download 15-minute OHLCV data from OANDA API or Yahoo Finance (2020-2025).
Saves to data/ohlcv/ with format: {SYMBOL}_M15_2020_2025.csv

Strategy:
1. OANDA API first (better data quality, official pricing) - for forex pairs
2. Yahoo Finance fallback (public data, no key needed) - for cryptos/indices/metals
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

# Load environment variables from .env.fiveers_live
load_dotenv(".env.fiveers_live", override=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

DATA_DIR = Path("data/ohlcv")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Limit range to the backtest window to speed up downloads
START_DATE = datetime(2023, 1, 1)
END_DATE = datetime(2025, 12, 31)

# OANDA API Configuration
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")

if OANDA_API_KEY:
    OANDA_URL = "https://api-fxpractice.oanda.com" if OANDA_ENVIRONMENT == "practice" else "https://api-fxtrade.oanda.com"
    log.info(f"✓ OANDA API key loaded ({OANDA_ENVIRONMENT} environment)")
else:
    OANDA_URL = None
    log.warning("⚠ OANDA_API_KEY not found - will use Yahoo Finance only")

# Symbols: restrict to 35 used in backtests to reduce runtime
FOREX_SYMBOLS = [
    "AUD_CAD", "AUD_CHF", "AUD_JPY", "AUD_NZD", "AUD_USD",
    "CAD_CHF", "CAD_JPY", "CHF_JPY",
    "EUR_AUD", "EUR_CAD", "EUR_CHF", "EUR_GBP", "EUR_JPY", "EUR_NZD", "EUR_USD",
    "GBP_AUD", "GBP_CAD", "GBP_CHF", "GBP_JPY", "GBP_NZD", "GBP_USD",
    "NZD_CAD", "NZD_CHF", "NZD_JPY", "NZD_USD",
    "USD_CAD", "USD_CHF", "USD_JPY",
    # Metals via OANDA
    "XAU_USD", "XAG_USD",
]

YAHOO_SYMBOLS = {
    # Cryptos
    "BTC_USD": "BTC-USD",
    "ETH_USD": "ETH-USD",
    # Indices
    "SPX500_USD": "^GSPC",
    "NAS100_USD": "^NDX",
    "UK100_USD": "^FTSE",
}

# Stooq symbols for indices (no auth, free)
STQ_SYMBOLS = {
    # Note: Stooq 1h intraday often unavailable; using daily fallback only
    # "SPX500_USD": "spx",
    # "NAS100_USD": "ndx", 
    # "UK100_USD": "ftse",
}

ALL_SYMBOLS = FOREX_SYMBOLS + list(YAHOO_SYMBOLS.keys())


# ═══════════════════════════════════════════════════════════════════════
# OANDA API DATA DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════

def download_from_oanda(symbol: str) -> Optional[pd.DataFrame]:
    """
    Download 15m data from OANDA API.
    OANDA API returns max 5000 candles per request.
    """
    if not OANDA_API_KEY or not OANDA_URL:
        return None
    
    try:
        log.debug(f"  → OANDA API ({symbol}, M15)...")
        headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
        dfs = []
        current_date = START_DATE

        while current_date < END_DATE:
            chunk_end = min(current_date + timedelta(days=3), END_DATE)
            from_ts = int(current_date.timestamp())
            to_ts = int(chunk_end.timestamp())

            url = f"{OANDA_URL}/v3/instruments/{symbol}/candles"
            params = {
                "price": "MBA",
                "granularity": "M15",
                "from": from_ts,
                "to": to_ts,
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                log.debug(f"    OANDA error: {response.status_code}")
                break

            candles = response.json().get("candles", [])
            if not candles:
                break

            rows = []
            for candle in candles:
                if candle.get("complete"):
                    rows.append({
                        "time": candle["time"],
                        "Open": float(candle["mid"]["o"]),
                        "High": float(candle["mid"]["h"]),
                        "Low": float(candle["mid"]["l"]),
                        "Close": float(candle["mid"]["c"]),
                        "Volume": 0,
                    })

            if rows:
                dfs.append(pd.DataFrame(rows))

            current_date = chunk_end

        if dfs:
            df = pd.concat(dfs, ignore_index=True)
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time").reset_index(drop=True)
            log.info(f"  ✓ OANDA: {len(df)} candles")
            return df

    except Exception as e:
        log.debug(f"  ⚠ OANDA error: {str(e)[:50]}")

    return None


# ═══════════════════════════════════════════════════════════════════════
# BINANCE API DATA DOWNLOAD (for Crypto - no key needed)
# ═══════════════════════════════════════════════════════════════════════

def download_from_binance(symbol: str) -> Optional[pd.DataFrame]:
    """
    Download crypto data from Binance API (no authentication required).
    Downloads 1h data and resamples to 15m.
    Symbols: BTC_USD, ETH_USD -> BTCUSDT, ETHUSDT
    """
    try:
        if "BTC" in symbol:
            binance_symbol = "BTCUSDT"
        elif "ETH" in symbol:
            binance_symbol = "ETHUSDT"
        else:
            return None
        
        log.debug(f"  → Binance ({binance_symbol}, 1h resampled to 15m)...")
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
            except Exception as e:
                log.debug(f"      Binance chunk error: {str(e)[:40]}")
                break
            current_date = chunk_end
        
        if not dfs:
            log.warning("  ✗ Binance: No data")
            return None
        
        df = pd.concat(dfs, ignore_index=True)
        df["time"] = pd.to_datetime(df["time"])
        df = df.drop_duplicates(subset=["time"], keep="last")
        df = df.sort_values("time").reset_index(drop=True)
        
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
        log.warning(f"  ✗ Binance error: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════
# STOOQ DATA DOWNLOAD (for Indices - no key needed)
# ═══════════════════════════════════════════════════════════════════════

def download_from_stooq(symbol: str) -> Optional[pd.DataFrame]:
    """Download 1h index data from Stooq and resample to 15m."""
    stq_symbol = STQ_SYMBOLS.get(symbol)
    if not stq_symbol:
        return None
    try:
        url = f"https://stooq.pl/q/d/l/?s={stq_symbol}&i=60"
        log.debug(f"  → Stooq ({stq_symbol}, 1h→15m)...")
        csv_bytes = requests.get(url, timeout=30).content
        if not csv_bytes:
            log.warning("  ✗ Stooq: empty response")
            return None
        df = pd.read_csv(BytesIO(csv_bytes))
        if df.empty:
            log.warning("  ✗ Stooq: No data")
            return None
        # Normalize columns
        cols_lower = {c.lower(): c for c in df.columns}
        date_col = cols_lower.get("date")
        time_col = cols_lower.get("time")
        if not date_col:
            log.warning("  ✗ Stooq: missing date column")
            return None
        if time_col:
            df["time"] = pd.to_datetime(df[date_col] + " " + df[time_col])
        else:
            df["time"] = pd.to_datetime(df[date_col])
        df = df.rename(columns={
            cols_lower.get("open", "Open"): "Open",
            cols_lower.get("high", "High"): "High",
            cols_lower.get("low", "Low"): "Low",
            cols_lower.get("close", "Close"): "Close",
            cols_lower.get("volume", "Volume"): "Volume",
        })
        df = df[["time", "Open", "High", "Low", "Close", "Volume"]]
        df = df.dropna(subset=["Close"])
        df = df[(df["time"] >= START_DATE) & (df["time"] <= END_DATE)]
        if df.empty:
            log.warning("  ✗ Stooq: filtered to empty range")
            return None
        df_15m = df.set_index("time").resample("15min").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).reset_index()
        df_15m = df_15m.dropna(subset=["Close"])
        log.info(f"  ✓ Stooq: {len(df_15m)} candles (1h→15m)")
        return df_15m
    except Exception as e:
        log.warning(f"  ✗ Stooq error: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════
# YAHOO FINANCE DATA DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════

def download_from_yahoo(symbol: str, yahoo_symbol: str) -> Optional[pd.DataFrame]:
    """
    Download from Yahoo Finance.
    - Daily data resampled to 15m (synthetic intraday)
    """
    try:
        log.debug(f"  → Yahoo ({yahoo_symbol}, daily→15m)...")
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
        
        # Handle MultiIndex columns from yfinance (multi-ticker downloads)
        if isinstance(df_daily.columns, pd.MultiIndex):
            # Flatten MultiIndex columns
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
        log.warning(f"  ✗ Yahoo error: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════
# SAVE DATA
# ═══════════════════════════════════════════════════════════════════════

def save_data(df: pd.DataFrame, symbol: str) -> Path:
    """Save DataFrame to CSV with standard format."""
    filename = DATA_DIR / f"{symbol}_M15_2020_2025.csv"
    
    # Ensure columns in correct order
    cols = ["time", "Open", "High", "Low", "Close", "Volume"]
    df = df[cols]
    
    # Save
    df.to_csv(filename, index=False, float_format="%.8f")
    
    log.info(f"✓ Saved: {filename.name}")
    return filename


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    log.info("="*80)
    log.info("DOWNLOADING 15-MINUTE DATA (2020-2025)")
    log.info("="*80)
    log.info(f"Total symbols: {len(ALL_SYMBOLS)}")
    log.info(f"  - Forex (OANDA): {len(FOREX_SYMBOLS)}")
    log.info(f"  - Yahoo fallback: {len(YAHOO_SYMBOLS)}")
    log.info(f"  - Stooq indices: {len(STQ_SYMBOLS)}")
    log.info(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    log.info("="*80)
    log.info("")
    
    results = {
        "oanda_success": [],
        "other_success": [],
        "partial": [],
        "failed": [],
    }
    
    # Download Forex from OANDA + Yahoo fallback
    for i, symbol in enumerate(FOREX_SYMBOLS, 1):
        log.info(f"\n[{i}/{len(ALL_SYMBOLS)}] {symbol} (Forex)")
        log.info("-" * 60)
        
        df = None
        source = None
        
        # Try OANDA
        if OANDA_API_KEY:
            df = download_from_oanda(symbol)
            if df is not None and len(df) > 100:
                source = "OANDA"
            else:
                log.debug(f"  ⚠ OANDA: insufficient data ({len(df) if df is not None else 0} rows)")
        
        # Save if we got enough data
        if df is not None and len(df) > 100:
            try:
                save_data(df, symbol)
                
                if len(df) > 5000:
                    results["oanda_success"].append(symbol)
                    log.info(f"✅ {source}: {len(df)} candles")
                else:
                    results["partial"].append((symbol, len(df)))
                    log.warning(f"⚠ {source}: {len(df)} candles (partial)")
            except Exception as e:
                results["failed"].append(symbol)
                log.error(f"✗ Save error: {e}")
        else:
            results["failed"].append(symbol)
            log.error(f"✗ OANDA: No sufficient data")
    
    # Download non-Forex from Binance/Stooq/Yahoo
    for i, (symbol, yahoo_sym) in enumerate(YAHOO_SYMBOLS.items(), len(FOREX_SYMBOLS)+1):
        log.info(f"\n[{i}/{len(ALL_SYMBOLS)}] {symbol} ({yahoo_sym})")
        log.info("-" * 60)
        
        df = None
        source = None
        
        # Try Binance for crypto
        if "BTC" in symbol or "ETH" in symbol:
            df = download_from_binance(symbol)
            if df is not None and len(df) > 100:
                source = "Binance"
        
        # Try Stooq for indices
        if df is None or len(df) < 100:
            df = download_from_stooq(symbol)
            if df is not None and len(df) > 100:
                source = "Stooq"
        
        # Fall back to Yahoo (daily->15m synthetic)
        if df is None or len(df) < 100:
            df = download_from_yahoo(symbol, yahoo_sym)
            if df is not None and len(df) > 100:
                source = "Yahoo"
        
        if df is not None and len(df) > 0:
            try:
                save_data(df, symbol)
                
                if len(df) > 1000:
                    results["other_success"].append(symbol)
                    log.info(f"✅ {source}: {len(df)} candles")
                else:
                    results["partial"].append((symbol, len(df)))
                    log.warning(f"⚠ {source}: {len(df)} candles (partial)")
            except Exception as e:
                results["failed"].append(symbol)
                log.error(f"✗ Save error: {e}")
        else:
            results["failed"].append(symbol)
            log.error(f"✗ Failed (no data)")
    
    # Summary
    log.info("\n" + "="*80)
    log.info("SUMMARY")
    log.info("="*80)
    total_success = len(results["oanda_success"]) + len(results["other_success"])
    log.info(f"✅ Success:  {total_success}/{len(ALL_SYMBOLS)} symbols")
    if results["oanda_success"]:
        log.info(f"   OANDA: {len(results['oanda_success'])} ({', '.join(results['oanda_success'][:5])}...)")
    if results["other_success"]:
        log.info(f"   Other: {len(results['other_success'])} ({', '.join(results['other_success'][:5])}...)")
    
    if results["partial"]:
        log.info(f"⚠  Partial:  {len(results['partial'])} symbols")
        for sym, cnt in results["partial"][:3]:
            log.info(f"   {sym}: {cnt} candles")
    
    if results["failed"]:
        log.info(f"✗ Failed:   {len(results['failed'])} symbols ({', '.join(results['failed'])})")
    
    log.info("="*80)
    log.info("\nNext step: Run backtest with M15 timeframe")
    log.info("  python scripts/backtest_main_live_bot.py --timeframe M15")


if __name__ == "__main__":
    main()
