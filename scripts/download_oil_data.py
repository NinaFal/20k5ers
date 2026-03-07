#!/usr/bin/env python3
"""
Download oil (Brent & WTI) OHLCV data from OANDA API.

Oanda names: BCO_USD (Brent), WTICO_USD (WTI)
5ers names:  XBR_USD (Brent), XTI_USD (WTI)

Downloads W1, D1, H4, M15 from 2022 to 2025.
Saves files with BOTH naming conventions for compatibility.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import requests
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env.fiveers_live", override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_API_URL = "https://api-fxpractice.oanda.com"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "ohlcv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Oanda instrument -> 5ers symbol mapping
INSTRUMENTS = {
    "BCO_USD": "XBR_USD",    # Brent Crude
    "WTICO_USD": "XTI_USD",  # WTI Crude
}

# Timeframes: oanda_granularity -> file_suffix, chunk_days
TIMEFRAMES = {
    "W":   ("W1",  None),     # Weekly - single request
    "D":   ("D1",  None),     # Daily - single request
    "H4":  ("H4",  365),      # 4-hour - yearly chunks
    "M15": ("M15", 3),        # 15-min - 3-day chunks
}

START_DATE = datetime(2022, 1, 1)
END_DATE = datetime(2025, 12, 31)


def download_candles(instrument: str, granularity: str, from_date: datetime, to_date: datetime) -> pd.DataFrame:
    """Download candles from OANDA API with chunked requests."""
    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
    url = f"{OANDA_API_URL}/v3/instruments/{instrument}/candles"

    _, chunk_days = TIMEFRAMES[granularity]

    all_rows = []
    current = from_date
    request_count = 0

    while current < to_date:
        if chunk_days:
            chunk_end = min(current + timedelta(days=chunk_days), to_date)
        else:
            chunk_end = to_date

        params = {
            "price": "M",
            "granularity": granularity,
            "from": current.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        for attempt in range(4):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 200:
                    break
                if resp.status_code == 429:  # Rate limited
                    wait = 2 ** (attempt + 1)
                    print(f"    Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                print(f"    Error {resp.status_code}: {resp.text[:100]}")
                break
            except requests.exceptions.RequestException as e:
                wait = 2 ** (attempt + 1)
                print(f"    Network error, retry in {wait}s: {e}")
                time.sleep(wait)
        else:
            print(f"    Failed after 4 retries, skipping chunk")
            current = chunk_end
            continue

        if resp.status_code != 200:
            current = chunk_end
            continue

        candles = resp.json().get("candles", [])
        for c in candles:
            if c.get("complete"):
                mid = c["mid"]
                all_rows.append({
                    "time": c["time"],
                    "Open": float(mid["o"]),
                    "High": float(mid["h"]),
                    "Low": float(mid["l"]),
                    "Close": float(mid["c"]),
                    "Volume": int(c.get("volume", 0)),
                })

        request_count += 1
        if request_count % 50 == 0:
            print(f"    {request_count} requests, {len(all_rows)} candles so far...")

        # Rate limiting: ~1 req/100ms
        time.sleep(0.15)

        if not chunk_days:
            break
        current = chunk_end

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    return df


def main():
    if not OANDA_API_KEY:
        print("ERROR: OANDA_API_KEY not found. Check .env.fiveers_live")
        sys.exit(1)

    print(f"Downloading oil data: {list(INSTRUMENTS.keys())}")
    print(f"Timeframes: {list(TIMEFRAMES.keys())}")
    print(f"Range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    for oanda_sym, fiveers_sym in INSTRUMENTS.items():
        print(f"{'='*60}")
        print(f"{oanda_sym} -> {fiveers_sym}")
        print(f"{'='*60}")

        for granularity, (tf_suffix, _) in TIMEFRAMES.items():
            filename = f"{fiveers_sym}_{tf_suffix}_2022_2025.csv"
            filepath = OUTPUT_DIR / filename

            if filepath.exists():
                existing = pd.read_csv(filepath)
                print(f"  {tf_suffix}: Already exists ({len(existing)} rows) - SKIPPING")
                continue

            print(f"  {tf_suffix}: Downloading...", end=" ", flush=True)
            df = download_candles(oanda_sym, granularity, START_DATE, END_DATE)

            if df.empty:
                print("NO DATA")
                continue

            df.to_csv(filepath, index=False)
            print(f"{len(df)} candles -> {filename}")

            # Also save with Oanda naming for reference
            oanda_filename = f"{oanda_sym}_{tf_suffix}_2022_2025.csv"
            oanda_path = OUTPUT_DIR / oanda_filename
            if not oanda_path.exists():
                df.to_csv(oanda_path, index=False)

        print()

    print("Done!")


if __name__ == "__main__":
    main()
