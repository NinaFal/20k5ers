#!/usr/bin/env python3
"""
Historical Data Downloader - 2015 t/m 2020

Downloads M15, H4, W1 en MN data van 2015 tot en met 2020 voor alle getraden
assets (exclusief BTC en ETH) ten behoeve van backtesten in die periode.

Bronnen:
  - OANDA API (practice) → forex pairs M15/H4/W1/MN
  - Yahoo Finance          → XAU, XAG, NAS100, BCO/XTI voor W1/MN/D1
                             (M15/H4 niet beschikbaar via Yahoo voor die periode)

Output bestanden: data/ohlcv/{SYMBOL}_{TF}_2015_2025.csv
  - Bestaande 2020-2025 bestanden worden automatisch samengevoegd
  - csv_data_provider herkent _2015_2025.csv patroon (zie update aldaar)

Gebruik:
    python scripts/download_historical_2015_2020.py
    python scripts/download_historical_2015_2020.py --tf M15     # alleen M15
    python scripts/download_historical_2015_2020.py --symbol EUR_USD
    python scripts/download_historical_2015_2020.py --dry-run    # toon wat er gedownload zou worden
"""

import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── OANDA configuratie ──────────────────────────────────────────────────────
# Laad vanuit .env.fiveers_live als de env vars nog niet zijn gezet
_env_file = Path(__file__).parent.parent / ".env.fiveers_live"
if _env_file.exists() and not os.getenv("OANDA_API_KEY"):
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")
OANDA_BASE_URL = (
    "https://api-fxtrade.oanda.com"
    if OANDA_ENVIRONMENT == "live"
    else "https://api-fxpractice.oanda.com"
)

# ─── Periodes ────────────────────────────────────────────────────────────────
START_DATE = datetime(2021, 1, 1, tzinfo=timezone.utc)
END_DATE   = datetime(2022, 12, 31, 23, 59, tzinfo=timezone.utc)

# ─── Alle getraden assets (OANDA formaat) ────────────────────────────────────
# BTC_USD en ETH_USD zijn op verzoek uitgesloten
TRADED_SYMBOLS = [
    # Forex Majors
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
    # EUR Crosses
    "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_AUD", "EUR_CAD", "EUR_NZD",
    # GBP Crosses
    "GBP_JPY", "GBP_CHF", "GBP_AUD", "GBP_CAD", "GBP_NZD",
    # AUD / NZD / CAD crosses
    "AUD_JPY", "AUD_CHF", "AUD_CAD", "AUD_NZD",
    "NZD_JPY", "NZD_CHF", "NZD_CAD",
    "CAD_JPY", "CAD_CHF", "CHF_JPY",
    # Metalen (alleen op OANDA live; hier via Yahoo Finance)
    "XAU_USD", "XAG_USD",
    # Indices (alleen via Yahoo Finance)
    "NAS100_USD",
    # Olie (via OANDA of Yahoo)
    "BCO_USD", "XTI_USD",
]

# OANDA-only symbols (werken op practice account)
# XAU_USD, XAG_USD, BCO_USD, NAS100_USD werken ook op practice; XTI_USD niet
OANDA_FOREX_SYMBOLS = [s for s in TRADED_SYMBOLS if s != "XTI_USD"]

# Yahoo Finance fallback — alleen XTI_USD (WTI olie niet beschikbaar op OANDA practice)
YAHOO_SYMBOLS = {
    "XTI_USD":   ("CL=F",  "WTI Crude Futures"),
}

# OANDA granulariteit codes
OANDA_GRANULARITIES = {
    "M15": "M15",
    "H4":  "H4",
    "W1":  "W",
    "MN":  "M",
}

# Yahoo Finance interval codes (alleen voor D1/W1/MN; H4/M15 niet beschikbaar historisch)
YAHOO_TIMEFRAMES = {
    "W1": "1wk",
    "MN": "1mo",
}

# Chunk-groottes per granulariteit (zodat we onder 5000 candles per request blijven)
CHUNK_DAYS = {
    "M15": 20,    # ~20d × 5×24×4 = 9600 → veilig voor forex (minder handelsuren)
    "H4":  180,   # ~6 maanden
    "W1":  730,   # ~2 jaar
    "MN":  1825,  # ~5 jaar
}

DATA_DIR = Path(__file__).parent.parent / "data" / "ohlcv"


# ─── OANDA download helpers ───────────────────────────────────────────────────

def oanda_candles(
    instrument: str,
    granularity: str,
    from_dt: datetime,
    to_dt: datetime,
) -> pd.DataFrame:
    """Download één chunk candledata van de OANDA v3 API."""
    url = f"{OANDA_BASE_URL}/v3/instruments/{instrument}/candles"
    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
    params = {
        "granularity": granularity,
        "from": from_dt.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "to":   to_dt.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "price": "M",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "?"
        print(f"    ⚠  HTTP {code} voor {instrument} {granularity}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"    ⚠  Fout: {e}")
        return pd.DataFrame()

    candles = data.get("candles", [])
    rows = []
    for c in candles:
        if not c.get("complete", False):
            continue
        rows.append({
            "time":   pd.to_datetime(c["time"], utc=True),
            "open":   float(c["mid"]["o"]),
            "high":   float(c["mid"]["h"]),
            "low":    float(c["mid"]["l"]),
            "close":  float(c["mid"]["c"]),
            "volume": int(c["volume"]),
        })
    return pd.DataFrame(rows)


def oanda_full_range(
    instrument: str,
    tf_key: str,              # "M15", "H4", "W1", "MN"
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Download alle candles in chunks en combineer."""
    gran  = OANDA_GRANULARITIES[tf_key]
    chunk = timedelta(days=CHUNK_DAYS[tf_key])
    parts = []
    cur   = start

    while cur < end:
        nxt = min(cur + chunk, end)
        df_chunk = oanda_candles(instrument, gran, cur, nxt)
        if not df_chunk.empty:
            parts.append(df_chunk)
        cur = nxt + timedelta(seconds=1)
        time.sleep(0.4)

    if not parts:
        return pd.DataFrame()

    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return df


# ─── Yahoo Finance helpers ────────────────────────────────────────────────────

def yahoo_download(
    symbol_key: str,
    tf_key: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Download data via yfinance voor metalen/indices/olie."""
    try:
        import yfinance as yf
    except ImportError:
        print("    Installeer yfinance: pip install yfinance")
        return pd.DataFrame()

    ticker_sym = YAHOO_SYMBOLS[symbol_key][0]
    interval   = YAHOO_TIMEFRAMES.get(tf_key)
    if not interval:
        # M15 / H4 historisch niet beschikbaar via Yahoo Finance
        return pd.DataFrame()

    try:
        df_raw = yf.download(
            ticker_sym,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"    ⚠  Yahoo fout voor {symbol_key}: {e}")
        return pd.DataFrame()

    if df_raw.empty:
        return pd.DataFrame()

    # Flatten multi-level columns indien aanwezig
    if isinstance(df_raw.columns, pd.MultiIndex):
        df_raw.columns = df_raw.columns.get_level_values(0)

    df = df_raw.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })[["open", "high", "low", "close", "volume"]].copy()

    df.index.name = "time"
    df = df.reset_index()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.dropna(subset=["open", "close"])
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return df


# ─── Bestand helpers ─────────────────────────────────────────────────────────

def find_existing_file(symbol: str, tf_key: str) -> Optional[Path]:
    """
    Zoek een bestaand databestand voor dit symbol + timeframe.
    Geeft het recentste bestand terug op basis van datum in bestandsnaam.
    """
    # Probeer verschillende naamconventies die in het project voorkomen
    sym_variants = [symbol, symbol.replace("_", "")]
    patterns_to_try = []
    for sv in sym_variants:
        patterns_to_try += [
            f"{sv}_{tf_key}_*.csv",
            f"{sv}_{tf_key}.csv",
        ]

    candidates = []
    for pat in patterns_to_try:
        candidates.extend(DATA_DIR.glob(pat))

    if not candidates:
        return None

    # Sorteer: voorkeur voor bestanden met de meeste jaren
    def sort_key(p: Path) -> tuple:
        name = p.stem
        # Geef voorkeur aan bestanden die vroeg beginnen
        parts = name.split("_")
        years = [int(x) for x in parts if x.isdigit() and len(x) == 4]
        start_yr = min(years) if years else 9999
        end_yr   = max(years) if years else 0
        return (start_yr, -end_yr)

    candidates.sort(key=sort_key)
    return candidates[0]


def load_existing(symbol: str, tf_key: str) -> pd.DataFrame:
    """Laad bestaand CSV bestand als DataFrame (lege DF als niet bestaat)."""
    path = find_existing_file(symbol, tf_key)
    if path is None:
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, parse_dates=["time"])
        df.columns = [c.lower() for c in df.columns]
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"    ⚠  Kon {path.name} niet laden: {e}")
        return pd.DataFrame()


def merge_and_save(
    new_df: pd.DataFrame,
    symbol: str,
    tf_key: str,
    existing_df: pd.DataFrame,
) -> Optional[Path]:
    """
    Voeg nieuwe data samen met bestaande data en sla op als
    {SYMBOL}_{TF}_2015_2025.csv (of _2015_2020.csv als er geen 2020+ data is).
    """
    if new_df.empty:
        return None

    parts = [new_df]
    if not existing_df.empty:
        parts.append(existing_df)

    combined = pd.concat(parts, ignore_index=True)
    combined["time"] = pd.to_datetime(combined["time"], utc=True)
    combined = combined.drop_duplicates("time").sort_values("time").reset_index(drop=True)

    # Bepaal jaarsuffix op basis van daadwerkelijke data
    min_year = combined["time"].dt.year.min()
    max_year = combined["time"].dt.year.max()
    out_name = f"{symbol}_{tf_key}_{min_year}_{max_year}.csv"
    out_path = DATA_DIR / out_name

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_path, index=False)
    return out_path


# ─── Hoofdlogica ──────────────────────────────────────────────────────────────

def process_symbol_tf(
    symbol: str,
    tf_key: str,
    dry_run: bool = False,
) -> bool:
    """Download + merge + sla op voor één symbol/timeframe combinatie."""
    is_yahoo_symbol = symbol in YAHOO_SYMBOLS
    supports_yahoo  = tf_key in YAHOO_TIMEFRAMES

    if dry_run:
        if is_yahoo_symbol and not supports_yahoo:
            print(f"    SKIP  {symbol} {tf_key}: niet beschikbaar via Yahoo (historisch M15/H4)")
        else:
            src = "Yahoo Finance" if (is_yahoo_symbol and supports_yahoo) else "OANDA"
            print(f"    PLAN  {symbol} {tf_key} via {src}")
        return True

    # Laad bestaande data voor eventuele merge
    existing = load_existing(symbol, tf_key)
    if not existing.empty:
        existing_start = existing["time"].min()
        # Check if data in the requested range is sufficiently present
        in_range = existing[(existing["time"] >= START_DATE) & (existing["time"] <= END_DATE)]
        if len(in_range) >= 100:  # at least 100 bars in range = data present
            print(f"    ✓ Al aanwezig vanaf {existing_start.date()} — overgeslagen")
            return True

    # Download nieuwe data
    if is_yahoo_symbol:
        if not supports_yahoo:
            print(f"    ⚠  {tf_key} historisch niet beschikbaar via Yahoo Finance → overgeslagen")
            return False
        print(f"    ↓ Yahoo Finance ({YAHOO_SYMBOLS[symbol][1]}) {tf_key} {START_DATE.year}–{END_DATE.year}...")
        new_df = yahoo_download(symbol, tf_key, START_DATE, END_DATE)
    else:
        print(f"    ↓ OANDA {tf_key} {START_DATE.year}–{END_DATE.year}...")
        new_df = oanda_full_range(symbol, tf_key, START_DATE, END_DATE)

    if new_df.empty:
        print(f"    ✗ Geen data ontvangen")
        return False

    # Sla op (merged met bestaande data)
    out_path = merge_and_save(new_df, symbol, tf_key, existing)
    if out_path:
        print(f"    ✓ Opgeslagen: {out_path.name} ({len(new_df)} nieuwe bars)")
        return True

    return False


def main():
    parser = argparse.ArgumentParser(description="Download historische data 2015-2020")
    parser.add_argument("--tf",     help="Alleen dit timeframe downloaden (M15, H4, W1, MN)")
    parser.add_argument("--symbol", help="Alleen dit symbol downloaden (bijv. EUR_USD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Laat zien wat gedownload zou worden zonder het te doen")
    args = parser.parse_args()

    # Valideer API key
    if not OANDA_API_KEY and not args.dry_run:
        print("❌ OANDA_API_KEY niet gevonden. Zorg dat .env.fiveers_live ingeladen is.")
        sys.exit(1)

    # Filter symbols
    symbols = TRADED_SYMBOLS
    if args.symbol:
        if args.symbol not in TRADED_SYMBOLS:
            print(f"❌ Onbekend symbol: {args.symbol}")
            print(f"   Beschikbaar: {', '.join(TRADED_SYMBOLS)}")
            sys.exit(1)
        symbols = [args.symbol]

    # Filter timeframes
    timeframes = list(OANDA_GRANULARITIES.keys())  # M15, H4, W1, MN
    if args.tf:
        if args.tf not in timeframes:
            print(f"❌ Onbekend timeframe: {args.tf}")
            print(f"   Beschikbaar: {', '.join(timeframes)}")
            sys.exit(1)
        timeframes = [args.tf]

    total   = len(symbols) * len(timeframes)
    done    = 0
    skipped = 0
    failed  = []

    print("=" * 70)
    print("HISTORISCHE DATA DOWNLOAD — 2015 t/m 2020")
    print("=" * 70)
    print(f"Symbols   : {len(symbols)}")
    print(f"Timeframes: {timeframes}")
    print(f"Periode   : {START_DATE.date()} → {END_DATE.date()}")
    print(f"Output    : {DATA_DIR}")
    print(f"OANDA env : {OANDA_ENVIRONMENT}")
    if args.dry_run:
        print("MODE      : DRY-RUN (niets wordt daadwerkelijk gedownload)")
    print("=" * 70)

    for sym in symbols:
        print(f"\n[{symbols.index(sym)+1}/{len(symbols)}] {sym}")
        for tf in timeframes:
            ok = process_symbol_tf(sym, tf, dry_run=args.dry_run)
            if ok:
                done += 1
            else:
                failed.append(f"{sym}_{tf}")

    print("\n" + "=" * 70)
    print("KLAAR")
    print("=" * 70)
    print(f"✓ Succesvol : {done}/{total}")
    if failed:
        print(f"✗ Mislukt   : {len(failed)}")
        for f in failed:
            print(f"  - {f}")
    print()
    print("Tip: voer daarna de backtest uit met:")
    print("  python backtest/src/main_live_bot_backtest.py \\")
    print("      --start 2015-01-01 --end 2020-12-31 --balance 20000")


if __name__ == "__main__":
    main()
