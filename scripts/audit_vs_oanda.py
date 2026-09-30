#!/usr/bin/env python3
"""
Legt de bestaande M15-bestanden naast verse OANDA-data om te zien of ze kloppen.

AANLEIDING. Twee keer in dit project bleek een bestand iets anders te bevatten
dan de naam beloofde: de cryptobestanden hielden uurbars vanaf 2023 onder de
naam "M15 vanaf 2020", en UK100 en SPX500 hielden dagbars. Beide keren viel dat
pas op toen er iemand keek. De vraag is dus gerechtvaardigd of de rest wel goed
is.

WAT ER GECONTROLEERD WORDT. Per symbool worden een paar vensters uit
verschillende jaren opgehaald bij OANDA en tegen het lokale bestand gelegd op
exact dezelfde tijdstempels. Gerapporteerd worden:

  dekking     hoeveel van de OANDA-bars ook lokaal bestaan. Laag betekent gaten
              of een verkeerde granulariteit.
  afwijking   mediane relatieve afwijking op de slotkoers. Nul betekent
              dezelfde bron; klein betekent mid tegen bid of een andere
              afrondingsconventie; groot betekent een ander instrument.
  bereik      mediane bar-hoogte lokaal tegen OANDA. Wijkt dat factoren af, dan
              staat er data van een andere timeframe in het bestand — precies
              hoe de dagbars in de M15-bestanden ontdekt zijn.

STEEKPROEF, GEEN VOLLEDIGE HERCONTROLE. Elf jaar M15 voor dertig symbolen
opnieuw ophalen is miljoenen bars. Vier vensters van een week per symbool,
gespreid over de jaren, vangt de fouten die er in dit project echt in zaten —
verkeerde granulariteit, verkeerd instrument, ontbrekende periodes — want die
zijn structureel en niet incidenteel.

Draaien:  uv run python3 scripts/audit_vs_oanda.py
"""
import json, os, statistics as st, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "ohlcv"
load_dotenv(ROOT / ".env.fiveers_live", override=True)
KEY = os.getenv("OANDA_API_KEY")
BASE = "https://api-fxpractice.oanda.com"

# Onze naam -> OANDA-naam waar die afwijkt.
ALIAS = {"UK100_USD": "UK100_GBP", "XBR_USD": "BCO_USD", "XTI_USD": "WTICO_USD"}
PROBES = [datetime(y, m, 6, tzinfo=timezone.utc)
          for y, m in ((2016, 3), (2019, 9), (2022, 5), (2024, 11))]


def fetch(inst, frm, to):
    q = urllib.parse.urlencode({"price": "M", "granularity": "M15",
                                "from": frm.isoformat().replace("+00:00", "Z"),
                                "to": to.isoformat().replace("+00:00", "Z")})
    req = urllib.request.Request(f"{BASE}/v3/instruments/{inst}/candles?{q}",
                                 headers={"Authorization": f"Bearer {KEY}"})
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                cs = json.load(r).get("candles", [])
            return pd.DataFrame(
                [(c["time"], float(c["mid"]["h"]), float(c["mid"]["l"]),
                  float(c["mid"]["c"])) for c in cs if c.get("complete")],
                columns=["time", "high", "low", "close"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** a); continue
            return None
        except Exception:
            if a == 2:
                return None
            time.sleep(2 ** a)
    return None


def local(sym):
    fs = sorted(D.glob(f"{sym}_M15_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    if not fs:
        return None
    d = pd.read_csv(fs[0])
    d.columns = [c.lower() for c in d.columns]
    d["time"] = pd.to_datetime(d["time"], utc=True, format="mixed")
    return d


def main():
    syms = sorted({p.name.split("_M15_")[0] for p in D.glob("*_M15_*.csv")})
    print(f"{'symbool':<13}{'lokaal':>9}{'oanda':>8}{'dekking':>9}"
          f"{'afwijk.close':>14}{'bereik lok/oan':>16}  oordeel")
    for sym in syms:
        loc = local(sym)
        if loc is None or loc.empty:
            print(f"{sym:<13}{'-':>9}  geen lokaal bestand"); continue
        inst = ALIAS.get(sym, sym)
        cov, dev, rng = [], [], []
        n_oanda = 0
        for p in PROBES:
            o = fetch(inst, p, p + timedelta(days=5))
            if o is None or o.empty:
                continue
            n_oanda += len(o)
            m = o.merge(loc, on="time", suffixes=("_o", "_l"))
            cov.append(len(m) / len(o))
            if len(m):
                dev += list(((m.close_l - m.close_o).abs() / m.close_o).dropna())
                rng.append(((m.high_l - m.low_l).median(),
                            (m.high_o - m.low_o).median()))
        if not cov:
            print(f"{sym:<13}{len(loc):>9}{'0':>8}  OANDA kent {inst} niet"); continue
        c = st.mean(cov) * 100
        dv = st.median(dev) * 100 if dev else float("nan")
        rl = st.median([r[0] for r in rng if r[1] > 0]) if rng else 0
        ro = st.median([r[1] for r in rng if r[1] > 0]) if rng else 0
        ratio = rl / ro if ro else float("nan")
        verdict = ("GEEN OVERLAP" if c < 5 else
                   "andere granulariteit" if ratio > 2 or ratio < 0.5 else
                   "gaten" if c < 90 else
                   "ander instrument" if dv > 1 else "ok")
        print(f"{sym:<13}{len(loc):>9}{n_oanda:>8}{c:>8.0f}%{dv:>13.3f}%"
              f"{ratio:>15.2f}  {verdict}", flush=True)
    print("\n[audit_vs_oanda] DONE_MARKER")


if __name__ == "__main__":
    main()
