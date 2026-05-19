#!/usr/bin/env python3
"""
Download 5-minute OHLCV data from OANDA API (2015-2025).
Saves to data/ohlcv/ as {SYMBOL}_M5_2015_2025.csv

All 33 backtest symbols are available on OANDA with M5 granularity.
Chunk size: 14 calendar days = ~2880 M5 bars (well under OANDA's 5000-candle limit).

Usage:
    python download_m5_data.py
    python download_m5_data.py --symbols EUR_USD USD_JPY   # specific symbols only
    python download_m5_data.py --skip-existing             # skip already downloaded
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(".env.fiveers_live", override=True)
except ImportError:
    pass  # env vars can be set externally

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

DATA_DIR = Path("data/ohlcv")
DATA_DIR.mkdir(parents=True, exist_ok=True)

GRANULARITY = "M5"
START_DATE  = datetime(2015, 1, 1)
END_DATE    = datetime(2025, 12, 31)
CHUNK_DAYS  = 14   # 14 cal days ≈ 10 trading days × 24h × 12 bars = 2880 M5 bars
REQUEST_DELAY = 0.25  # seconds between OANDA requests to avoid rate-limiting

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
_env = os.getenv("OANDA_ENVIRONMENT", "live")
OANDA_URL = "https://api-fxpractice.oanda.com" if _env == "practice" else "https://api-fxtrade.oanda.com"


# All 33 symbols that have M15_2015_2025 data (all available on OANDA)
ALL_SYMBOLS = [
    # Forex majors
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD",
    "AUD_USD", "NZD_USD",
    # Forex crosses
    "EUR_GBP", "EUR_JPY", "EUR_AUD", "EUR_CAD", "EUR_CHF", "EUR_NZD",
    "GBP_JPY", "GBP_AUD", "GBP_CAD", "GBP_CHF", "GBP_NZD",
    "AUD_JPY", "AUD_CAD", "AUD_CHF", "AUD_NZD",
    "NZD_JPY", "NZD_CAD", "NZD_CHF",
    "CAD_JPY", "CAD_CHF", "CHF_JPY",
    # Metals
    "XAU_USD", "XAG_USD",
    # Indices
    "NAS100_USD",
    # Oil (Brent)
    "BCO_USD", "XBR_USD",
]

# ═══════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════

def download_symbol(symbol: str) -> pd.DataFrame | None:
    """Download M5 data for one symbol from OANDA, 2015→2025."""
    if not OANDA_API_KEY:
        log.error("OANDA_API_KEY not set — cannot download")
        return None

    headers = {"Authorization": f"Bearer {OANDA_API_KEY}", "Connection": "close"}
    url = f"{OANDA_URL}/v3/instruments/{symbol}/candles"

    chunks = []
    current = START_DATE
    total_requests = 0
    retries_total = 0

    while current < END_DATE:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS), END_DATE)
        # OANDA: when both 'from' and 'to' are given, do NOT include 'count'
        params = {
            "price":       "M",          # mid-point prices
            "granularity": GRANULARITY,
            "from":        current.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to":          chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        for attempt in range(5):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=60)
                if resp.status_code == 404:
                    log.warning(f"  [{symbol}] Instrument not found on OANDA (404) — skipping")
                    return None
                if resp.status_code == 400:
                    log.debug(f"  [{symbol}] Bad request {resp.status_code}: {resp.text[:80]}")
                    break
                if resp.status_code != 200:
                    log.warning(f"  [{symbol}] HTTP {resp.status_code} — retry {attempt+1}/5")
                    time.sleep(2 ** attempt)
                    retries_total += 1
                    continue

                candles = resp.json().get("candles", [])
                rows = [
                    {
                        "time":   c["time"],
                        "open":   float(c["mid"]["o"]),
                        "high":   float(c["mid"]["h"]),
                        "low":    float(c["mid"]["l"]),
                        "close":  float(c["mid"]["c"]),
                        "volume": int(c.get("volume", 0)),
                    }
                    for c in candles if c.get("complete")
                ]
                if rows:
                    chunks.append(pd.DataFrame(rows))
                total_requests += 1
                break
            except requests.exceptions.RequestException as e:
                log.warning(f"  [{symbol}] Network error: {e} — retry {attempt+1}/5")
                time.sleep(2 ** attempt)
                retries_total += 1

        current = chunk_end
        time.sleep(REQUEST_DELAY)

    if not chunks:
        log.error(f"  [{symbol}] No data received")
        return None

    df = pd.concat(chunks, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    log.info(f"  [{symbol}] {len(df):,} M5 bars — {total_requests} requests"
             + (f" ({retries_total} retries)" if retries_total else ""))
    return df


def save(df: pd.DataFrame, symbol: str) -> Path:
    path = DATA_DIR / f"{symbol}_M5_2015_2025.csv"
    df.to_csv(path, index=False, float_format="%.8f")
    log.info(f"  [{symbol}] Saved → {path.name}")
    return path


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Download M5 OANDA data 2015-2025")
    parser.add_argument("--symbols", nargs="+", default=None, help="Specific symbols only")
    parser.add_argument("--skip-existing", action="store_true", help="Skip already downloaded files")
    args = parser.parse_args()

    symbols = args.symbols or ALL_SYMBOLS

    if not OANDA_API_KEY:
        log.error("❌ OANDA_API_KEY not found in .env.fiveers_live")
        sys.exit(1)

    log.info("=" * 70)
    log.info(f"M5 DOWNLOAD: {len(symbols)} symbols | {START_DATE.date()} → {END_DATE.date()}")
    log.info(f"Chunks: {CHUNK_DAYS} days each | Delay: {REQUEST_DELAY}s | URL: {OANDA_URL}")
    log.info("=" * 70)

    ok, skipped, failed = [], [], []

    for i, sym in enumerate(symbols, 1):
        out_path = DATA_DIR / f"{sym}_M5_2015_2025.csv"

        if args.skip_existing and out_path.exists():
            sz = out_path.stat().st_size / 1024 / 1024
            log.info(f"[{i}/{len(symbols)}] {sym} — SKIP (exists, {sz:.1f} MB)")
            skipped.append(sym)
            continue

        log.info(f"\n[{i}/{len(symbols)}] {sym}")
        df = download_symbol(sym)

        if df is not None and len(df) > 1000:
            save(df, sym)
            ok.append(sym)
        elif df is not None:
            log.warning(f"  [{sym}] Only {len(df)} bars — saving anyway")
            save(df, sym)
            ok.append(sym)
        else:
            failed.append(sym)

    # Summary
    log.info("\n" + "=" * 70)
    log.info(f"DONE: {len(ok)} OK | {len(skipped)} skipped | {len(failed)} failed")
    if failed:
        log.warning(f"Failed: {', '.join(failed)}")
    if ok:
        log.info(f"OK:    {', '.join(ok)}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
