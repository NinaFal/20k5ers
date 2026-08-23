#!/usr/bin/env python3
"""
Hoe dicht zat de bot ooit bij het maximum aantal lots dat 5ers toestaat?

Dit is een andere vraag dan die van w5_margin_vs_equity.py, en de juiste. Die
vroeg of het TOTALE margegebruik ooit boven de 100% kwam — een vraag die
impliciet aanneemt dat er zoiets als een liquidatieniveau is. Dat is niet wat
5ers beschrijft. Support schreef:

    "You can open as many positions as you wish as long as the account leverage
     allows you. The account will reject the trade if you already used all the
     leverage."
    "Max Lot Size = (Account Balance x Leverage) / (Contract Size x Current Price)"

Dat is een plafond op wat je kunt OPENEN, geen mechanisme dat bestaande posities
sluit. De relevante vraag is dus niet "loopt de marge vol" maar "vraagt de bot
ooit een positie aan die groter is dan wat er nog past".

Twee grenzen, allebei gemeten:

  PER SYMBOOL   de formule van 5ers hierboven, tegen de balans op dat moment.
                Dit is het plafond als je verder niets openstaan hebt.

  CUMULATIEF    de marge van deze positie plus alles wat al openstaat, tegen de
                equity. Een order wordt geweigerd zodra de vrije marge kleiner
                is dan wat de order vraagt, dus het echte plafond ligt op 100%.

Draaien:  uv run python3 backtest/src/w5_maxlot_headroom.py
"""
import csv, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_m = importlib.util.spec_from_file_location("mr", str(HERE / "w5_margin_real.py"))
mr = importlib.util.module_from_spec(_m); _m.loader.exec_module(mr)


def analyse(path, start_balance, label):
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
        ev.append((r["open_time"], 1, r["symbol"], v, pr, 0.0))
        ev.append((r["close_time"], 0, r["symbol"], v, pr, pnl))
    ev.sort(key=lambda x: (x[0], x[1]))

    bal, used = start_balance, 0.0
    worst_sym, ws = 0.0, None          # lots gevraagd / lots toegestaan
    worst_cum, wc = 0.0, None          # marge na deze order / balans
    per_class = {}
    for t, is_open, sym, v, pr, pnl in ev:
        m = mr.margin_per_lot(sym, pr) * v
        if is_open:
            allowed = bal / mr.margin_per_lot(sym, pr) if mr.margin_per_lot(sym, pr) > 0 else 1e9
            frac = v / allowed if allowed > 0 else 9.99
            if frac > worst_sym:
                worst_sym, ws = frac, (t, sym, v, allowed, bal)
            k = mr.klass(sym)
            d = per_class.setdefault(k, {"n": 0, "worst": 0.0, "at": None})
            d["n"] += 1
            if frac > d["worst"]:
                d["worst"] = frac; d["at"] = (sym, v, allowed, bal)
            used += m
            cum = used / bal if bal > 0 else 9.99
            if cum > worst_cum:
                worst_cum, wc = cum, (t, used, bal)
        else:
            used -= m
            bal += pnl

    print(f"\n  {label}   start ${start_balance:,.0f}")
    if ws:
        t, sym, v, allowed, b = ws
        print(f"    zwaarste ENKELE order t.o.v. het symboolplafond   {worst_sym*100:>6.1f}%")
        print(f"      {sym} {v:.2f} lots, toegestaan {allowed:,.1f} lots bij een balans "
              f"van ${b:,.0f}   ({t})")
    if wc:
        t, u, b = wc
        print(f"    zwaarste CUMULATIEVE marge t.o.v. de balans        {worst_cum*100:>6.1f}%"
              f"   (${u:,.0f} van ${b:,.0f}, {t})")
    print(f"    {'klasse':<11}{'orders':>7}{'krapste order':>16}   waar")
    for k in sorted(per_class, key=lambda x: -per_class[x]["worst"]):
        d = per_class[k]; sym, v, allowed, b = d["at"]
        print(f"    {k:<11}{d['n']:>7}{d['worst']*100:>15.1f}%   "
              f"{sym} {v:.2f} van {allowed:,.1f} lots")
    return worst_sym, worst_cum


def main():
    print("=" * 78)
    print("RUIMTE TOT HET PLAFOND VAN 5ERS — niet 'loopt de marge vol' maar")
    print("'vraagt de bot ooit meer lots aan dan er passen'")
    print("=" * 78)
    files = sorted(mr.CACHE.glob("*.csv"))
    if not files:
        print("\n  geen gecachete trades — draai eerst w5_margin_real.py")
        return
    worst_s = worst_c = 0.0
    for f in files:
        year, bal = f.stem.split("_")
        a, b = analyse(f, float(bal), year)
        worst_s, worst_c = max(worst_s, a), max(worst_c, b)
    print("\n" + "-" * 78)
    print(f"  Hoogste enkele order t.o.v. het symboolplafond : {worst_s*100:.1f}%"
          f"   ({1/worst_s:.1f}x ruimte)" if worst_s else "")
    print(f"  Hoogste cumulatieve marge t.o.v. de balans     : {worst_c*100:.1f}%"
          f"   ({1/worst_c:.1f}x ruimte)" if worst_c else "")
    print(f"  Weigering treedt op bij 100% cumulatief.")
    print("\n[w5_maxlot_headroom] DONE_MARKER")


if __name__ == "__main__":
    main()
