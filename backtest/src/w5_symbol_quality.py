#!/usr/bin/env python3
"""
Winratio, verwachtingswaarde en stabiliteit per symbool.

DRIE VALKUILEN, want dit is de gevaarlijkste analyse in dit project.

1. WINRATIO ZEGT WEINIG. Een symbool met 90% winners en af en toe een verlies
   van tien keer de gemiddelde winst is netto negatief. Daarom staat de
   verwachtingswaarde per trade er altijd naast, en de profit factor. Alleen
   winratio lezen is hoe je jezelf om de tuin leidt.

2. MEER RISICO OP WINNAARS UIT HET VERLEDEN IS OVERFITTEN. Als je op de
   toppresteerders van de afgelopen tien jaar zwaarder gaat inzetten, optimaliseer
   je op de rangschikking van deze ene steekproef. De enige bescherming daartegen
   is kijken of een symbool in BEIDE helften goed is en of de rangschikking zelf
   stabiel is. Die correlatie staat onderaan; is die laag, dan is de rangschikking
   ruis en heeft differentieren per symbool geen basis.

3. KLEINE AANTALLEN. Symbolen met minder dan honderd trades over elf jaar staan
   apart, want daar is een winratio van 70% net zo goed toeval.

Draaien:  uv run python3 backtest/src/w5_symbol_quality.py
"""
import csv, importlib.util, json, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

CACHE = w5.W5_DIR / "per_symbol_trades"
SPLIT = 2020
MIN_TRADES = 100


def stats(v):
    if not v:
        return None
    wins = [x for x in v if x > 0]; loss = [x for x in v if x <= 0]
    gp = sum(wins); gl = -sum(loss)
    return {"n": len(v), "win": len(wins) / len(v) * 100, "pnl": sum(v),
            "exp": sum(v) / len(v),
            "pf": (gp / gl) if gl > 0 else float("inf"),
            "avg_win": st.mean(wins) if wins else 0.0,
            "avg_loss": st.mean(loss) if loss else 0.0}


def main():
    halves = {"vroeg": defaultdict(list), "laat": defaultdict(list)}
    files = sorted(CACHE.glob("*.csv"))
    if not files:
        print("geen trades — draai eerst w5_per_symbol.py"); return
    for p in files:
        year = int(p.stem)
        half = "vroeg" if year < SPLIT else "laat"
        for r in csv.DictReader(open(p)):
            try:
                pnl = float(r["pnl"] or 0) + float(r["swap"] or 0)
            except (ValueError, TypeError):
                continue
            halves[half][r["symbol"]].append(pnl)

    syms = sorted(set(halves["vroeg"]) | set(halves["laat"]))
    rows = []
    for s in syms:
        a = halves["vroeg"][s]; b = halves["laat"][s]
        rows.append((s, stats(a), stats(b), stats(a + b)))
    big = [r for r in rows if r[3] and r[3]["n"] >= MIN_TRADES]
    small = [r for r in rows if r[3] and r[3]["n"] < MIN_TRADES]
    big.sort(key=lambda r: -r[3]["exp"])

    print("=" * 108)
    print(f"KWALITEIT PER SYMBOOL — 2015-2025, minstens {MIN_TRADES} trades")
    print("=" * 108)
    print(f"\n{'symbool':<12}{'trades':>7}{'win%':>7}{'verw/trade':>12}{'PF':>7}"
          f"{'gem win':>10}{'gem verlies':>12}"
          f"{'   |':>4}{'win% vroeg':>11}{'win% laat':>10}{'verw vroeg':>12}{'verw laat':>11}")
    for s, a, b, t in big:
        wa = f"{a['win']:.0f}" if a else "-"; wb = f"{b['win']:.0f}" if b else "-"
        ea = f"${a['exp']:,.0f}" if a else "-"; eb = f"${b['exp']:,.0f}" if b else "-"
        print(f"{s:<12}{t['n']:>7}{t['win']:>6.1f}%${t['exp']:>11,.0f}{t['pf']:>7.2f}"
              f"${t['avg_win']:>9,.0f}${t['avg_loss']:>11,.0f}{'   |':>4}"
              f"{wa:>11}{wb:>10}{ea:>12}{eb:>11}")

    if small:
        print(f"\n  Te weinig trades om iets over te zeggen (<{MIN_TRADES}):")
        for s, a, b, t in sorted(small, key=lambda r: -r[3]["n"]):
            print(f"    {s:<12}{t['n']:>5} trades  win {t['win']:.0f}%  "
                  f"verw ${t['exp']:,.0f}")

    # Is de rangschikking stabiel? Zonder dat heeft differentieren geen basis.
    pairs = [(a["exp"], b["exp"]) for s, a, b, t in big
             if a and b and a["n"] >= 30 and b["n"] >= 30]
    if len(pairs) > 3:
        xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
        mx, my = st.mean(xs), st.mean(ys)
        cov = sum((x - mx) * (y - my) for x, y in pairs) / len(pairs)
        cor = cov / (st.pstdev(xs) * st.pstdev(ys))
        print(f"\n  STABILITEIT VAN DE RANGSCHIKKING")
        print(f"  correlatie verwachtingswaarde 2015-2019 tegen 2020-2025: {cor:+.2f}"
              f"  ({len(pairs)} symbolen)")
        print(f"  1,0 = wie goed was blijft goed. 0,0 = de volgorde is ruis en")
        print(f"  differentieren per symbool heeft geen basis.")
        top = sorted(big, key=lambda r: -r[1]["exp"] if r[1] else 0)[:8]
        kept = sum(1 for r in top if r[2] and r[2]["exp"] > st.median(
            [x[2]["exp"] for x in big if x[2]]))
        print(f"  van de 8 beste symbolen in 2015-2019 zit {kept} boven de mediaan in 2020-2025")

    print("\n[w5_symbol_quality] DONE_MARKER")


if __name__ == "__main__":
    main()
