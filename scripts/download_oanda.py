#!/usr/bin/env python3
"""
Haalt candles bij OANDA op — dezelfde bron als de rest van de dataset.

WAAROM OANDA EN NIET DUKASCOPY. De goede M15-bestanden in dit project komen van
OANDA. Voor een instrument een tweede aanbieder gebruiken zou de dagtrend op een
andere tape zetten dan de M15 waarop gehandeld wordt — precies waarom de
Yahoo-dagbestanden bij crypto in quarantaine gingen. Dukascopy levert bovendien
ticks: per instrument tienduizenden LZMA-bestanden die zelf geaggregeerd moeten
worden, en dat is de stap waar een fout ongemerkt insluipt.

TICKERNAMEN. Twee instrumenten stonden onder een naam die OANDA niet kent, en
dat is de echte reden dat hun data ontbrak:

    UK100_USD  ->  bestaat niet. De FTSE 100 heet UK100_GBP.
    XBR_USD    ->  bestaat niet. Brent heet BCO_USD.

Dat laatste staat zelfs in config.py als comment ("Brent Crude (BCO_USD on
OANDA)"), maar die naam werd bij het downloaden nergens gebruikt. Het
downloadscript viel daardoor terug op Yahoo, dat alleen dagbars kon leveren, en
schreef die weg onder een M15-naam.

CONVENTIE, gelijk aan download_m15_data.py: mid-prijzen, alleen candles met
complete=true, tijden in UTC.

Draaien:  uv run python3 scripts/download_oanda.py UK100_GBP:UK100_USD
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ohlcv"
load_dotenv(ROOT / ".env.fiveers_live", override=True)
KEY = os.getenv("OANDA_API_KEY")
BASE = ("https://api-fxpractice.oanda.com"
        if os.getenv("OANDA_ENVIRONMENT", "practice") == "practice"
        else "https://api-fxtrade.oanda.com")

# OANDA-granulariteit -> onze bestandsnaam
GRANS = {"M15": "M15", "H4": "H4", "D": "D1", "W": "W1", "M": "MN"}
START = datetime(2015, 1, 1, tzinfo=timezone.utc)


def fetch(inst, gran, frm, to):
    q = urllib.parse.urlencode({"price": "M", "granularity": gran,
                                "from": frm.isoformat().replace("+00:00", "Z"),
                                "to": to.isoformat().replace("+00:00", "Z")})
    req = urllib.request.Request(f"{BASE}/v3/instruments/{inst}/candles?{q}",
                                 headers={"Authorization": f"Bearer {KEY}"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("candles", [])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt); continue
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return []


def download(inst, gran):
    """Haalt de hele reeks op in blokken. OANDA geeft maximaal 5000 candles per
    verzoek, dus de blokgrootte is per granulariteit zo gekozen dat hij daar
    ruim onder blijft."""
    span = {"M15": timedelta(days=40), "H4": timedelta(days=400),
            "D": timedelta(days=2000), "W": timedelta(days=5000),
            "M": timedelta(days=5000)}[gran]
    rows, cur, now = [], START, datetime.now(timezone.utc)
    while cur < now:
        end = min(cur + span, now)
        for c in fetch(inst, gran, cur, end):
            if not c.get("complete"):
                continue
            m = c["mid"]
            rows.append((c["time"], float(m["o"]), float(m["h"]),
                         float(m["l"]), float(m["c"]), int(c.get("volume", 0))))
        cur = end
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], utc=True, format="mixed")
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def main():
    if not KEY:
        raise SystemExit("OANDA_API_KEY niet gezet")
    if len(sys.argv) < 2:
        raise SystemExit("geef paren op als OANDA_NAAM:ONZE_NAAM")
    for spec in sys.argv[1:]:
        inst, ours = spec.split(":") if ":" in spec else (spec, spec)
        print(f"\n{inst}  ->  {ours}", flush=True)
        for gran, tf in GRANS.items():
            try:
                df = download(inst, gran)
            except Exception as e:
                print(f"  {tf:<4}FOUT {e}", flush=True); continue
            if df is None or df.empty:
                print(f"  {tf:<4}geen data", flush=True); continue
            p = OUT / f"{ours}_{tf}_{df.time.min().year}_{df.time.max().year}.csv"
            df.to_csv(p, index=False)
            print(f"  {tf:<4}{len(df):>8} bars  {df.time.min().date()} .. "
                  f"{df.time.max().date()}  -> {p.name}", flush=True)
    print("\n[download_oanda] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
