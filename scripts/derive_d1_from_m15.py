#!/usr/bin/env python3
"""
Leidt dagbars af uit de M15-reeks die er al ligt.

WAAROM DIT BETER IS DAN DOWNLOADEN. Brent heeft M15, H4 en W1 van 2015 tot 2025,
maar D1 pas vanaf 2022. De confluentie eist minstens 50 dagbars
(`main_live_bot_backtest.py:3842`), dus Brent kan voor 2022 geen signaal geven —
wat de decade-arm bevestigde: 2015 tot en met 2021 waren cent voor cent gelijk
aan de arm zonder olie.

Een D1-bestand bij een andere aanbieder halen zou werken, maar dan komt de
dagtrend van een andere tape dan de M15 waarop gehandeld wordt. Dat is precies
het probleem waarvoor de Yahoo-D1-bestanden bij crypto in quarantaine gingen.
Afleiden uit de eigen M15 kan niet uit de pas lopen met zichzelf.

DE DAGGRENS IS HET ENIGE LASTIGE. Brokerdagbars lopen niet van middernacht tot
middernacht maar van 22:00 UTC tot 22:00 UTC in de winter en 21:00 tot 21:00 in
de zomer — dat is middernacht op een MT5-server die op EET/EEST staat. Het
bestaande D1-bestand bevestigt dat: alle tijdstempels staan op uur 21 of 22.
Groeperen op kalenderdatum in UTC zou dus bars opleveren die vier uur verschoven
zijn ten opzichte van wat de broker rapporteert.

Daarom wordt er gegroepeerd op de datum in Europe/Athens en krijgt elke bar de
tijdstempel van middernacht daar, terugvertaald naar UTC.

GECONTROLEERD, NIET AANGENOMEN. Voor de overlappende periode wordt de afgeleide
reeks vergeleken met het echte D1-bestand. Wijkt open, high, low of close meer
af dan een marge, dan stopt het script — want dan klopt de aanname over de
daggrens niet en is de rest van de reeks ook verdacht.

Draaien:  uv run python3 scripts/derive_d1_from_m15.py XBR_USD
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "ohlcv"
TZ = "Europe/Athens"          # standaard MT5-servertijd, EET/EEST
TOL = 0.002                   # 0,2% afwijking toegestaan bij de verificatie


def load(path):
    d = pd.read_csv(path)
    d.columns = [c.lower() for c in d.columns]
    d["time"] = pd.to_datetime(d["time"], utc=True, format="mixed")
    return d.sort_values("time").reset_index(drop=True)


def derive(m15):
    t = m15["time"].dt.tz_convert(TZ)
    m15 = m15.assign(_day=t.dt.normalize())
    g = m15.groupby("_day").agg(open=("open", "first"), high=("high", "max"),
                                low=("low", "min"), close=("close", "last"),
                                volume=("volume", "sum")).reset_index()
    g["time"] = g["_day"].dt.tz_convert("UTC")
    return g[["time", "open", "high", "low", "close", "volume"]]


def verify(derived, real):
    m = derived.merge(real, on="time", suffixes=("_d", "_r"))
    if m.empty:
        print("  GEEN overlap om tegen te verifieren — gestopt")
        return False
    bad = {}
    for c in ("open", "high", "low", "close"):
        rel = ((m[f"{c}_d"] - m[f"{c}_r"]).abs() / m[f"{c}_r"])
        bad[c] = (rel > TOL).sum()
        print(f"    {c:<6} mediaan afwijking {rel.median()*100:>6.3f}%   "
              f"boven {TOL*100:.1f}%: {bad[c]:>4} van {len(m)}")
    ok = all(v / len(m) < 0.02 for v in bad.values())
    print(f"  overlap {len(m)} dagen — {'AKKOORD' if ok else 'AFGEKEURD'}")
    return ok


def derive_mn(m15):
    """Maandbars. De confluentie leest MN1 mee; zonder dat bestand valt de
    maandtrend terug op 'mixed' en beslist de richting op minder informatie."""
    t = m15["time"].dt.tz_convert(TZ)
    m15 = m15.assign(_m=t.dt.to_period("M").dt.start_time.dt.tz_localize(TZ))
    g = m15.groupby("_m").agg(open=("open", "first"), high=("high", "max"),
                              low=("low", "min"), close=("close", "last"),
                              volume=("volume", "sum")).reset_index()
    g["time"] = g["_m"].dt.tz_convert("UTC")
    return g[["time", "open", "high", "low", "close", "volume"]]


def main():
    sym = sys.argv[1] if len(sys.argv) > 1 else "XBR_USD"
    m15s = sorted(D.glob(f"{sym}_M15_*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    if not m15s:
        raise SystemExit(f"geen M15 voor {sym}")
    m15 = load(m15s[0])
    print(f"{sym}: M15 uit {m15s[0].name} — {len(m15)} bars "
          f"{m15.time.min().date()} .. {m15.time.max().date()}")

    derived = derive(m15)
    print(f"  afgeleid: {len(derived)} dagbars "
          f"{derived.time.min().date()} .. {derived.time.max().date()}")
    print(f"  tijdstempel-uren: {sorted(derived.time.dt.hour.unique())}")

    reals = sorted(D.glob(f"{sym}_D1_*.csv"))
    if reals:
        real = load(reals[0])
        print(f"\n  verificatie tegen {reals[0].name} ({len(real)} bars):")
        if not verify(derived, real):
            raise SystemExit("  afgeleide bars komen niet overeen — niets weggeschreven")
    else:
        print("\n  geen bestaand D1-bestand om tegen te verifieren")

    out = D / f"{sym}_D1_{derived.time.min().year}_{derived.time.max().year}.csv"
    derived.to_csv(out, index=False)
    print(f"\n  geschreven: {out.name}  ({len(derived)} bars)")
    if not list(D.glob(f"{sym}_MN_*.csv")):
        mn = derive_mn(m15)
        mo = D / f"{sym}_MN_{mn.time.min().year}_{mn.time.max().year}.csv"
        mn.to_csv(mo, index=False)
        print(f"  geschreven: {mo.name}  ({len(mn)} maandbars)")

    if reals and reals[0].name != out.name:
        print(f"  LET OP: {reals[0].name} staat er nog. De loader plakt beide aan")
        print(f"  elkaar en laat bij dubbele tijdstempels de laatste winnen, dus")
        print(f"  het oude bestand moet weg voordat dit gebruikt wordt.")


if __name__ == "__main__":
    main()
