#!/usr/bin/env python3
"""
Wat draagt elk symbool bij, en blijft dat zo in de tweede helft?

WAARSCHUWING VOORAF, want dit is precies het soort analyse dat overfit. De
slechtste tickers uit een reeks knippen levert altijd een mooier plaatje op —
ook als de rangschikking puur ruis is. Met 28 symbolen en ~1.100 trades per jaar
haalt de helft per definitie de onderste helft, en niets in dat feit voorspelt
volgend jaar.

Daarom wordt hier niets gerapporteerd zonder de reeks in tweeen te knippen:

  2015-2019   eerste helft
  2020-2025   tweede helft

Een symbool dat in BEIDE helften geld kost is een kandidaat. Een symbool dat in
een van beide slecht is en in de andere goed, is ruis en moet je met rust laten.
Dat onderscheid is het enige wat deze analyse kan dragen.

Het is ook precies de test die de drie bestaande uitsluitingen ooit doorstonden
(AUD_NZD, EUR_NZD, AUD_JPY, "structureel net-negatief in beide helften"). De
fxpairs-arm laat inmiddels zien dat ze terugzetten weinig verandert: bij gelijk
kapitaal $325 winst per trade tegen $331 zonder. Dat is een nuchtere herinnering
aan wat deze analyse waard is — hij vindt symbolen die in het verleden slecht
waren, niet symbolen die in de toekomst slecht zullen zijn.

DE BALANS WORDT DOORGEROLD, en een eerdere versie deed dat niet. Die draaide elk
jaar los op $50.000 om te voorkomen dat late jaren zwaarder wegen puur door
positiegrootte. Dat loste iets op en brak iets ergers: zonder de scalingladder
die een gefund account beschermt, liep een slecht begin tegen de 10%-muur en was
de rekening dood voor de rest van dat jaar. 2016 stopte op 10 maart na 311
trades, 2019 op 13 februari na 174, 2022 op 10 augustus — tegen 1.600 tot 1.970
in de volle jaren.

De blootstelling was daarmee ongeveer 4,3 jaar waar het er zes leek, en welk
symbool toevallig actief was in zo'n kort venster woog onevenredig zwaar. UK100
kwam daardoor op $20 per trade uit over drie jaar en op $144 over zes, en dat
verschil zei niets over UK100.

Nu bereikt het account de cap en overleeft het alle elf jaar, net als in
w5_decade_crypto.py, dus is elk jaar even lang. Late jaren handelen wel met meer
kapitaal, maar dat geldt voor alle symbolen gelijk en vertekent de onderlinge
vergelijking niet.

Draaien:  uv run python3 backtest/src/w5_per_symbol.py
"""
import csv, importlib.util, json, os, shutil, statistics as st, subprocess, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

YEARS = list(range(2015, 2026))
SPLIT = 2020                      # 2015-2019 tegen 2020-2025
CACHE = w5.W5_DIR / "per_symbol_trades"
OUT = w5.W5_DIR / "per_symbol.json"
# Alles aan wat 5ers aanbiedt, ook wat nu uitstaat — anders kun je niet zien of
# uitsluiten terecht was. Olie zit hardgecodeerd uit in de engine (:2789) en
# krijg je hier dus niet te zien.
# Standaard de LIVE uitsluitingslijst, zodat de bijdrage per symbool gemeten
# wordt in de configuratie die ook echt gehandeld wordt. Positielimieten en de
# cumulatieve risicocap maken symbolen namelijk afhankelijk van elkaar: een
# symbool erbij verdringt trades van een ander, dus een studie met andere
# symbolen aan meet een ander universum dan het jouwe.
#
# W5_STUDY_EXCLUDE overschrijft dit, bijvoorbeeld om te zien wat een
# uitgesloten symbool zou hebben gedaan.
EXCL_FOR_STUDY = os.getenv("W5_STUDY_EXCLUDE") or w5.BASE_ENV["EXCLUDE_SYMBOLS"]


def run_year(year, balance=50_000.0):
    cached = CACHE / f"{year}.csv"
    if cached.exists():
        return cached
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(w5.BASE_ENV); e.update(b["env"])
    e["EXCLUDE_SYMBOLS"] = EXCL_FOR_STUDY
    e["FIVEERS_MAX_SCALE"] = "500000"; e["CFG_DAILY_WALL_PCT"] = "5.0"
    e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp}); e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"psym_{year}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST), "--start", f"{year}-01-01",
                    "--end", f"{year}-12-31", "--balance", f"{balance:.2f}",
                    "--output", str(d), "--quiet"], env=e, cwd=str(w5.cs.dh.REPO),
                   capture_output=True, text=True, timeout=14400)
    tc, rj = d / "trades.csv", d / "results.json"
    nxt = balance
    if rj.exists():
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        nxt = (log[-1]["new_level"] if log else balance)
    if tc.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        shutil.copy(tc, cached)
        (CACHE / f"{year}.level").write_text(str(nxt))
    shutil.rmtree(d, ignore_errors=True)
    return cached if cached.exists() else None


def main():
    halves = {"vroeg": defaultdict(list), "laat": defaultdict(list)}
    years_done = []
    bal = 50_000.0
    for y in YEARS:
        p = run_year(y, bal)
        lv = CACHE / f"{y}.level"
        if lv.exists():
            bal = float(lv.read_text())
        if not p:
            print(f"  {y}: geen trades.csv", flush=True); continue
        years_done.append(y)
        half = "vroeg" if y < SPLIT else "laat"
        n = 0
        for r in csv.DictReader(open(p)):
            try:
                pnl = float(r["pnl"] or 0) + float(r["swap"] or 0)
            except (ValueError, TypeError):
                continue
            halves[half][r["symbol"]].append(pnl)
            n += 1
        print(f"  {y} ({half}): {n} trades", flush=True)

    if not years_done:
        print("niets gedraaid"); return

    syms = sorted(set(halves["vroeg"]) | set(halves["laat"]))

    def stats(v):
        if not v:
            return None
        return {"n": len(v), "pnl": sum(v), "per": sum(v) / len(v),
                "win": sum(1 for x in v if x > 0) / len(v) * 100,
                "worst": min(v), "sd": st.pstdev(v) if len(v) > 1 else 0.0}

    rows = []
    for s in syms:
        a, b = stats(halves["vroeg"][s]), stats(halves["laat"][s])
        rows.append((s, a, b))
    rows.sort(key=lambda r: ((r[1]["pnl"] if r[1] else 0) + (r[2]["pnl"] if r[2] else 0)))

    print("\n" + "=" * 104, flush=True)
    print(f"PER SYMBOOL — {years_done[0]}-{years_done[-1]}, elk jaar los op $50.000", flush=True)
    print("=" * 104, flush=True)
    print(f"\n{'symbool':<12}{'2015-2019':>28}{'2020-2025':>28}{'':>10}")
    print(f"{'':<12}{'trades':>8}{'pnl':>11}{'/trade':>9}{'trades':>8}{'pnl':>11}{'/trade':>9}"
          f"{'beide neg':>12}{'nu uit':>9}")
    excl_now = set(w5.BASE_ENV["EXCLUDE_SYMBOLS"].split(","))
    both_neg = []
    for s, a, b in rows:
        an = f"{a['n']:>8}" if a else f"{'-':>8}"
        ap = f"${a['pnl']:>10,.0f}" if a else f"{'-':>11}"
        aa = f"${a['per']:>8,.0f}" if a else f"{'-':>9}"
        bn = f"{b['n']:>8}" if b else f"{'-':>8}"
        bp = f"${b['pnl']:>10,.0f}" if b else f"{'-':>11}"
        ba = f"${b['per']:>8,.0f}" if b else f"{'-':>9}"
        neg = bool(a and b and a["pnl"] < 0 and b["pnl"] < 0)
        if neg:
            both_neg.append(s)
        print(f"{s:<12}{an}{ap}{aa}{bn}{bp}{ba}{('JA' if neg else ''):>12}"
              f"{('ja' if s in excl_now else ''):>9}")

    print(f"\n  Negatief in BEIDE helften: {both_neg or 'geen'}", flush=True)
    print(f"  Nu al uitgesloten:         {sorted(excl_now & set(syms)) or 'geen van deze'}", flush=True)
    new = [s for s in both_neg if s not in excl_now]
    print(f"  Kandidaat, nog niet uit:   {new or 'geen'}", flush=True)

    print(f"\n  Risico per symbool — slechtste enkele trade en spreiding (hele periode):", flush=True)
    print(f"  {'symbool':<12}{'trades':>8}{'slechtste':>12}{'sd':>10}{'sd/trade-gem':>14}", flush=True)
    risk = []
    for s in syms:
        v = halves["vroeg"][s] + halves["laat"][s]
        if len(v) < 30:
            continue
        risk.append((s, len(v), min(v), st.pstdev(v)))
    for s, n, wst, sd in sorted(risk, key=lambda r: r[2])[:10]:
        print(f"  {s:<12}{n:>8}${wst:>11,.0f}${sd:>9,.0f}", flush=True)

    json.dump({"years": years_done, "split": SPLIT,
               "both_negative": both_neg, "excluded_now": sorted(excl_now)},
              open(OUT, "w"), indent=1)
    print("\n[w5_per_symbol] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
