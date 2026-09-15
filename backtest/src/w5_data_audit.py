#!/usr/bin/env python3
"""
Vergelijkt wat elk M15-databestand BELOOFT met wat erin zit.

Aanleiding: BTC_USD_M15_2020_2025.csv heet M15 en heet 2020, maar bevat uurbars
vanaf 2023. Dat soort verschil valt nergens op — de loader slikt het, de
backtest draait door, en het symbool handelt gewoon veel minder vaak dan je
denkt zonder dat iets waarschuwt.

Per bestand gecontroleerd: eerste en laatste datum, aantal bars, de mediane
afstand tussen twee bars (0:15 hoort M15 te zijn) en of de tijdstempels een
tijdzone dragen. Alles wat afwijkt van de bestandsnaam wordt gemarkeerd.

Draaien vanuit de repo-root:  uv run python3 backtest/src/w5_data_audit.py
"""
import pandas as pd, re, collections
from pathlib import Path
D = Path("data/ohlcv")
rows = []
for f in sorted(D.glob("*_M15*.csv")):
    try:
        d = pd.read_csv(f, parse_dates=['time'])
    except Exception:
        d = pd.read_csv(f); d.columns=[c.lower() for c in d.columns]
        d['time']=pd.to_datetime(d['time'])
    d.columns = [c.lower() for c in d.columns]
    t = pd.to_datetime(d['time'])
    tz = "aware" if t.dt.tz is not None else "NAIEF"
    if t.dt.tz is not None: t = t.dt.tz_convert(None)
    gaps = t.diff().dropna()
    med = gaps.median()
    m = re.search(r"_M15_(\d{4})_(\d{4})", f.name)
    claim = f"{m.group(1)}-{m.group(2)}" if m else "-"
    rows.append((f.name, claim, str(t.min())[:10], str(t.max())[:10], len(d),
                 str(med), tz))
print(f"{'bestand':<34}{'naam zegt':<11}{'echt van':<12}{'tot':<12}{'bars':>8}  {'mediaan spacing':<17}{'tz'}")
for r in rows:
    flag = ""
    if r[1] != "-" and not r[2].startswith(r[1][:4]): flag = "  <-- START WIJKT AF"
    if "0 days 00:15" not in r[5]: flag += "  <-- GEEN M15"
    print(f"{r[0]:<34}{r[1]:<11}{r[2]:<12}{r[3]:<12}{r[4]:>8}  {r[5]:<17}{r[6]}{flag}")
