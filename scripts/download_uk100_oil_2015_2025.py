#!/usr/bin/env python3
"""
Download UK100 and oil (XBR/XTI) data from 2015-2025 for all timeframes.

Strategy:
- XBR_USD: copy from existing BCO_USD files (already 2015-2025)
- XTI_USD: download WTICO_USD from OANDA from 2015-2025
- UK100_USD: download from OANDA from 2015-2025

Timeframes: MN, W1, D1, H4, M15

Usage:
    python scripts/download_uk100_oil_2015_2025.py
"""

import os
import sys
import time
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env.fiveers_live", override=True)

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_API_URL = "https://api-fxtrade.oanda.com"  # live endpoint for indices/oil
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "ohlcv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = datetime(2015, 1, 1)
END_DATE = datetime(2025, 12, 31)

# OANDA granularity -> (file_suffix, chunk_days)
TIMEFRAMES = {
    "M":   ("MN",  None),   # Monthly - single request
    "W":   ("W1",  None),   # Weekly  - single request
    "D":   ("D1",  365*2),  # Daily   - 2-year chunks
    "H4":  ("H4",  365),    # 4-hour  - yearly chunks
    "M15": ("M15", 3),      # 15-min  - 3-day chunks
}


def download_candles(instrument: str, granularity: str,
                     from_date: datetime, to_date: datetime) -> pd.DataFrame:
    """Download candles from OANDA API with chunked requests."""
    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
    url = f"{OANDA_API_URL}/v3/instruments/{instrument}/candles"
    _, chunk_days = TIMEFRAMES[granularity]

    all_rows = []
    current = from_date
    request_count = 0

    while current < to_date:
        chunk_end = min(current + timedelta(days=chunk_days), to_date) if chunk_days else to_date

        params = {
            "price": "M",
            "granularity": granularity,
            "from": current.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        resp = None
        for attempt in range(4):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 200:
                    break
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    print(f"    Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                print(f"    HTTP {resp.status_code}: {resp.text[:120]}")
                break
            except requests.exceptions.RequestException as e:
                wait = 2 ** (attempt + 1)
                print(f"    Network error, retry in {wait}s: {e}")
                time.sleep(wait)

        if resp is None or resp.status_code != 200:
            current = chunk_end
            continue

        for c in resp.json().get("candles", []):
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
        if request_count % 100 == 0:
            print(f"    {request_count} requests, {len(all_rows)} candles so far...")

        time.sleep(0.15)  # ~6 req/s rate limit

        if not chunk_days:
            break
        current = chunk_end

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    return df


def copy_bco_to_xbr():
    """Copy existing BCO_USD files to XBR_USD naming (2015-2025)."""
    print("=" * 60)
    print("XBR_USD: Copying from existing BCO_USD files")
    print("=" * 60)

    mappings = [
        ("BCO_USD_M15_2015_2025.csv",  "XBR_USD_M15_2015_2025.csv"),
        ("BCO_USD_H4_2015_2025.csv",   "XBR_USD_H4_2015_2025.csv"),
        ("BCO_USD_W1_2014_2025.csv",   "XBR_USD_W1_2015_2025.csv"),
    ]

    for src_name, dst_name in mappings:
        src = OUTPUT_DIR / src_name
        dst = OUTPUT_DIR / dst_name

        if dst.exists():
            print(f"  {dst_name}: already exists - SKIP")
            continue

        if not src.exists():
            print(f"  {dst_name}: source {src_name} not found - SKIP")
            continue

        # Filter to 2015+ if source starts earlier
        df = pd.read_csv(src)
        df["time"] = pd.to_datetime(df["time"])
        df = df[df["time"] >= "2015-01-01"].reset_index(drop=True)
        df.to_csv(dst, index=False)
        print(f"  {dst_name}: {len(df)} rows copied from {src_name}")

    # Download missing BCO/XBR timeframes (D1 and MN not available from 2015)
    missing = [
        ("BCO_USD", "XBR_USD", "D",  "D1",  "XBR_USD_D1_2015_2025.csv"),
        ("BCO_USD", "XBR_USD", "M",  "MN",  "XBR_USD_MN_2015_2025.csv"),
    ]
    for oanda_sym, fiveers_sym, gran, tf, fname in missing:
        fpath = OUTPUT_DIR / fname
        if fpath.exists():
            print(f"  {fname}: already exists - SKIP")
            continue
        print(f"  {fname}: downloading {oanda_sym} {gran}...", end=" ", flush=True)
        df = download_candles(oanda_sym, gran, START_DATE, END_DATE)
        if df.empty:
            print("NO DATA")
        else:
            df.to_csv(fpath, index=False)
            print(f"{len(df)} candles")

    print()


def download_wtico_to_xti():
    """Download WTICO_USD 2015-2025 and save as XTI_USD."""
    print("=" * 60)
    print("XTI_USD: Downloading WTICO_USD 2015-2025")
    print("=" * 60)

    for gran, (tf_suffix, _) in TIMEFRAMES.items():
        fname = f"XTI_USD_{tf_suffix}_2015_2025.csv"
        fpath = OUTPUT_DIR / fname

        if fpath.exists():
            print(f"  {fname}: already exists - SKIP")
            continue

        print(f"  {fname}: downloading WTICO_USD {gran}...", end=" ", flush=True)
        df = download_candles("WTICO_USD", gran, START_DATE, END_DATE)

        if df.empty:
            print("NO DATA")
            # Try BCO as fallback (similar price profile)
            continue

        df.to_csv(fpath, index=False)
        # Also save WTICO naming
        wtico_path = OUTPUT_DIR / f"WTICO_USD_{tf_suffix}_2015_2025.csv"
        if not wtico_path.exists():
            df.to_csv(wtico_path, index=False)
        print(f"{len(df)} candles")

    print()


def download_uk100():
    """Download UK100_USD 2015-2025 for all timeframes."""
    print("=" * 60)
    print("UK100_USD: Downloading 2015-2025")
    print("=" * 60)

    for gran, (tf_suffix, _) in TIMEFRAMES.items():
        fname = f"UK100_USD_{tf_suffix}_2015_2025.csv"
        fpath = OUTPUT_DIR / fname

        if fpath.exists():
            print(f"  {fname}: already exists - SKIP")
            continue

        print(f"  {fname}: downloading UK100_USD {gran}...", end=" ", flush=True)
        df = download_candles("UK100_USD", gran, START_DATE, END_DATE)

        if df.empty:
            print("NO DATA (index may require live OANDA account)")
            continue

        df.to_csv(fpath, index=False)
        print(f"{len(df)} candles")

    print()


def main():
    if not OANDA_API_KEY:
        print("ERROR: OANDA_API_KEY not found. Check .env.fiveers_live")
        sys.exit(1)

    print("=" * 60)
    print("DOWNLOAD UK100 + OIL DATA — 2015-2025")
    print("=" * 60)
    print(f"  API URL: {OANDA_API_URL}")
    print(f"  Output:  {OUTPUT_DIR}")
    print(f"  Period:  {START_DATE.date()} → {END_DATE.date()}")
    print(f"  TFs:     MN, W1, D1, H4, M15")
    print()

    copy_bco_to_xbr()
    download_wtico_to_xti()
    download_uk100()

    print("=" * 60)
    print("Done! New files in data/ohlcv/:")
    for f in sorted(OUTPUT_DIR.glob("*2015_2025*")):
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"  {f.name:45s} {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
