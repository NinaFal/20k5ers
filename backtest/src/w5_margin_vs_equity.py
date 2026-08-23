#!/usr/bin/env python3
"""
Piekmarge afgezet tegen de balans OP DAT MOMENT, niet tegen de startbalans.

w5_margin_real.py deelde de piekmarge door de startbalans. Dat overdrijft: een
account dat in januari op $50.000 begint en in juli op $140.000 staat, heeft in
juli ook bijna drie keer zoveel vrije marge. De 221% uit dat script is dus geen
221% van wat er op het piekmoment beschikbaar was.

Hier wordt de balans meegelopen: startbalans plus alle gerealiseerde pnl en swap
van trades die voor het meetmoment gesloten zijn. Dat is de balans, niet de
equity — het verschil is de zwevende pnl van de op dat moment open posities, die
niet uit trades.csv te reconstrueren is zonder de koersreeks opnieuw te lezen.
Voor een marge-uitspraak is dat aanvaardbaar: bij een winnend boek is de equity
hoger dan de balans en is deze meting conservatief; bij een verliezend boek
lager, en dan onderschat hij de druk.

Wat de vraag echt is: op welk moment was gebruikte marge / beschikbare marge het
hoogst, en kwam die verhouding boven 1? Boven 1 betekent dat 5ers de volgende
trade zou hebben geweigerd en dat de backtest een boek aanhield dat het account
niet kon dragen.

Draaien:  uv run python3 backtest/src/w5_margin_vs_equity.py
"""
import csv, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_m = importlib.util.spec_from_file_location("mr", str(HERE / "w5_margin_real.py"))
mr = importlib.util.module_from_spec(_m); _m.loader.exec_module(mr)

CACHE = mr.CACHE


def analyse(path, start_balance, label):
    rows = list(csv.DictReader(open(path)))
    # Gebeurtenissen: open (+marge), close (-marge, +pnl).
    ev = []
    for r in rows:
        try:
            v, pr = float(r["volume"]), float(r["open_price"])
            pnl = float(r["pnl"] or 0) + float(r["swap"] or 0)
        except (ValueError, TypeError):
            continue
        if not (r["open_time"] and r["close_time"]) or pr <= 0:
            continue
        m = mr.margin_per_lot(r["symbol"], pr) * v
        ev.append((r["open_time"], 1, m, 0.0, r["symbol"]))
        ev.append((r["close_time"], 0, m, pnl, r["symbol"]))
    ev.sort(key=lambda x: (x[0], x[1]))

    bal = start_balance
    used = 0.0
    worst_ratio, worst = 0.0, None
    peak_abs, peak_abs_t = 0.0, None
    for t, is_open, m, pnl, sym in ev:
        if is_open:
            used += m
            r = used / bal if bal > 0 else 99
            if r > worst_ratio:
                worst_ratio, worst = r, (t, used, bal, sym)
            if used > peak_abs:
                peak_abs, peak_abs_t = used, t
        else:
            used -= m
            bal += pnl

    t, u, b, sym = worst
    print(f"\n  {label}   start ${start_balance:,}")
    print(f"    hoogste marge/balans-verhouding   {worst_ratio * 100:>6.1f}%")
    print(f"      op {t}   marge ${u:,.0f}   balans ${b:,.0f}   laatste opening {sym}")
    print(f"    piekmarge in dollars              ${peak_abs:>10,.0f}  op {peak_abs_t}")
    print(f"    eindbalans                        ${bal:>10,.0f}")
    print(f"    {'BOVEN 100% — 5ers had geweigerd' if worst_ratio > 1 else 'onder 100% — geen weigering'}")
    return worst_ratio


def challenge_phase(path, start_balance, label, cap_mult=1.10):
    """De eerste fase, zolang de balans onder cap_mult x start blijft.

    Dit is het stuk dat er voor de challenge toe doet. Zodra het account naar
    $150.000 is gegroeid is marge geen thema meer; de vraag is of een account
    van $50.000 dat naar $54.000 moet, het boek kan dragen dat de backtest
    aanhoudt. Daar is de balans klein en de marge relatief het zwaarst.
    """
    rows = list(csv.DictReader(open(path)))
    ev = []
    for r in rows:
        try:
            v, pr = float(r["volume"]), float(r["open_price"])
            pnl = float(r["pnl"] or 0) + float(r["swap"] or 0)
        except (ValueError, TypeError):
            continue
        if not (r["open_time"] and r["close_time"]) or pr <= 0:
            continue
        m = mr.margin_per_lot(r["symbol"], pr) * v
        ev.append((r["open_time"], 1, m, 0.0, r["symbol"]))
        ev.append((r["close_time"], 0, m, pnl, r["symbol"]))
    ev.sort(key=lambda x: (x[0], x[1]))

    ceiling = start_balance * cap_mult
    bal, used = start_balance, 0.0
    worst_ratio, worst = 0.0, None
    biggest_single, bs = 0.0, None
    for t, is_open, m, pnl, sym in ev:
        if bal > ceiling:
            break
        if is_open:
            used += m
            r = used / bal if bal > 0 else 99
            if r > worst_ratio:
                worst_ratio, worst = r, (t, used, bal, sym)
            if m / bal > biggest_single:
                biggest_single, bs = m / bal, (t, sym, m, bal)
        else:
            used -= m
            bal += pnl
    if worst is None:
        print(f"\n  {label} challengefase: geen trades onder de grens")
        return
    t, u, b, sym = worst
    print(f"\n  {label} CHALLENGEFASE (balans tot ${ceiling:,.0f})")
    print(f"    hoogste marge/balans        {worst_ratio * 100:>6.1f}%   "
          f"op {t}  (${u:,.0f} van ${b:,.0f})")
    if bs:
        bt, bsym, bm, bb = bs
        print(f"    zwaarste enkele positie     {biggest_single * 100:>6.1f}%   "
              f"{bsym} ${bm:,.0f} op een balans van ${bb:,.0f}  ({bt})")
    print(f"    {'BOVEN 100% — 5ers had geweigerd' if worst_ratio > 1 else 'onder 100% — geen weigering'}")


def main():
    print("=" * 74)
    print("MARGE TEGEN DE BALANS OP HET MOMENT ZELF")
    print("=" * 74)
    for f in sorted(CACHE.glob("*.csv")):
        year, bal = f.stem.split("_")
        analyse(f, float(bal), f"{year}")

    print("\n" + "=" * 74)
    print("ALLEEN DE CHALLENGEFASE — het account is hier op zijn kleinst")
    print("=" * 74)
    for f in sorted(CACHE.glob("*.csv")):
        year, bal = f.stem.split("_")
        challenge_phase(f, float(bal), f"{year}")
    print("\n[w5_margin_vs_equity] DONE_MARKER")


if __name__ == "__main__":
    main()
