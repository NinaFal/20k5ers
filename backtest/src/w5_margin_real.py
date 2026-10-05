#!/usr/bin/env python3
"""
Margecontrole met de ECHTE 5ers-hefbomen (bevestigd door support).

  Forex              1:100
  Indices en Metals  1:25
  Commodities        1:5
  Crypto             1:2

Elke eerdere margeberekening in dit project ging uit van 1:100 op ALLES en kwam
op 69,4% piekgebruik tijdens de klim. Metals en indices vragen vier keer zoveel
marge, crypto vijftig keer. Die 69,4% is dus een onderschatting.

Waarom dit ertoe doet: 5ers weigert de trade als de marge op is ("The account
will reject the trade if you already used all the leverage"). De simulator
modelleert marge helemaal niet — csv_mt5_simulator.py:557-559 zet margin op 0,0
en margin_free op de volledige equity — dus de backtest opent posities die live
geweigerd zouden worden.

Formule van 5ers: Max Lot = (Balance x Leverage) / (Contract Size x Price)
Marge per lot     = notional in USD / hefboom

NOTIONAL, en waarom een eerdere versie hier de mist in ging. Voor FX is de
notional de contractgrootte in de BASISVALUTA, omgerekend naar USD — niet
contractgrootte maal de genoteerde prijs. Voor USD_JPY is de notional $100.000,
niet 100.000 x 110 = $11 miljoen. Die fout blies FX-marge met een factor 110 op
en produceerde een piek van 5.368% van de balans, wat onzin was. Alleen paren
met USD als quote (EUR_USD) hebben notional = 100.000 x prijs; voor de rest
telt de USD-waarde van de basisvaluta.

Crossparen worden omgerekend met indicatieve langetermijnkoersen. Dat is grof —
GBP stond in tien jaar tussen 1,20 en 1,70 — maar de vraag hier is of het
piekgebruik in de buurt van 100% komt, en daar verandert 20% koersruis niets aan.

Draaien:  uv run python3 backtest/src/w5_margin_real.py
"""
import csv, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

LEVERAGE = {"FX": 100, "METAL": 25, "INDEX": 25, "COMMODITY": 5, "CRYPTO": 2}

# Niet-FX contractgroottes, overgenomen uit csv_mt5_simulator.py.
CONTRACT = {"XAU": 100, "XAG": 5000, "NAS100": 1, "US30": 1, "UK100": 1,
            "SPX500": 1, "XBR": 100, "XTI": 100, "BTC": 1, "ETH": 1,
            "XRP": 1, "ADA": 1}

# Indicatieve USD-waarde van een eenheid basisvaluta, voor crossparen.
USD_RATE = {"USD": 1.0, "EUR": 1.12, "GBP": 1.30, "AUD": 0.72, "NZD": 0.66,
            "CAD": 0.76, "CHF": 1.05, "JPY": 0.0080}

CACHE = w5.W5_DIR / "margin_trades"


def klass(sym):
    u = (sym or "").upper().replace("_", "")
    if any(x in u for x in ("XAU", "XAG")):                      return "METAL"
    if any(x in u for x in ("NAS100", "US30", "UK100", "SPX")):  return "INDEX"
    if any(x in u for x in ("XBR", "XTI", "BCO", "WTICO")):      return "COMMODITY"
    if any(x in u for x in ("BTC", "ETH", "XRP", "ADA")):        return "CRYPTO"
    return "FX"


def notional_usd(sym, price):
    """USD-waarde van een positie van 1,00 lot."""
    u = (sym or "").upper()
    k = klass(sym)
    if k != "FX":
        for name, cs in CONTRACT.items():
            if name in u.replace("_", ""):
                return cs * price
        return 100_000 * price
    # FX: 100.000 eenheden basisvaluta, omgerekend naar USD.
    base = u.split("_")[0] if "_" in u else u[:3]
    quote = u.split("_")[1] if "_" in u else u[3:6]
    if quote == "USD":
        return 100_000 * price          # prijs IS de USD-waarde van de basis
    if base == "USD":
        return 100_000                  # basis is al USD
    return 100_000 * USD_RATE.get(base, 1.0)


def margin_per_lot(sym, price):
    return notional_usd(sym, price) / LEVERAGE[klass(sym)]


def run(balance, year):
    """Draait een jaar en bewaart trades.csv, zodat heranalyse gratis is."""
    cached = CACHE / f"{year}_{balance}.csv"
    if cached.exists():
        return list(csv.DictReader(open(cached)))
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(w5.BASE_ENV); e.update(b["env"])
    e["CFG_DAILY_WALL_PCT"] = "5.0"; e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp}); e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"marg_{year}_{balance}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST), "--start", f"{year}-01-01",
                    "--end", f"{year}-12-31", "--balance", str(balance),
                    "--output", str(d), "--quiet"], env=e, cwd=str(w5.cs.dh.REPO),
                   capture_output=True, text=True, timeout=7200)
    tc = d / "trades.csv"
    rows = []
    if tc.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        shutil.copy(tc, cached)
        rows = list(csv.DictReader(open(cached)))
    shutil.rmtree(d, ignore_errors=True)
    return rows


def analyse(rows, balance, label):
    cols = list(rows[0].keys()) if rows else []
    ot = next((c for c in cols if "open" in c and "time" in c), None)
    ct = next((c for c in cols if "close" in c and "time" in c), None)
    vc = next((c for c in cols if c in ("volume", "lots", "lot_size", "size")), None)
    pc = next((c for c in cols if c in ("open_price", "entry_price", "entry", "price")), None)
    sc = next((c for c in cols if "symbol" in c), None)
    if not all((ot, ct, vc, pc, sc)):
        print(f"  {label}: kolommen ontbreken -> {sorted(cols)[:14]}")
        return None
    ev, per_class = [], {}
    for r in rows:
        try:
            v, pr = float(r[vc]), float(r[pc])
        except (ValueError, TypeError):
            continue
        if not (r[ot] and r[ct]) or pr <= 0:
            continue
        m = margin_per_lot(r[sc], pr) * v
        ev.append((r[ot], 1, m)); ev.append((r[ct], 0, m))
        k = klass(r[sc])
        d = per_class.setdefault(k, {"n": 0, "maxlot": 0.0, "maxmargin": 0.0, "sum": 0.0})
        d["n"] += 1; d["maxlot"] = max(d["maxlot"], v)
        d["maxmargin"] = max(d["maxmargin"], m); d["sum"] += m
    ev.sort(key=lambda x: (x[0], x[1]))
    cur = peak = 0.0; peak_t = None
    for t, o, m in ev:
        cur += m if o else -m
        if cur > peak:
            peak, peak_t = cur, t
    print(f"\n  {label}  (balans ${balance:,})")
    print(f"    piek gelijktijdige marge  ${peak:>12,.0f}   = {peak / balance * 100:>6.1f}% van de balans")
    print(f"    {'BOVEN 100% — 5ers zou trades geweigerd hebben' if peak > balance else 'onder 100% — geen weigering'}")
    print(f"    piekmoment {peak_t}")
    print(f"    {'klasse':<11}{'trades':>7}{'max lot':>10}{'max marge/pos':>16}{'gem marge/pos':>16}")
    for k in sorted(per_class, key=lambda x: -per_class[x]["maxmargin"]):
        d = per_class[k]
        print(f"    {k:<11}{d['n']:>7}{d['maxlot']:>10.2f}${d['maxmargin']:>15,.0f}"
              f"${d['sum'] / d['n']:>15,.0f}")
    return peak


def main():
    print("Marge per lot bij de ECHTE hefbomen (indicatieve prijzen):")
    for sym, pr in (("EUR_USD", 1.10), ("USD_JPY", 110.0), ("GBP_JPY", 145.0),
                    ("XAU_USD", 2000), ("XAG_USD", 25),
                    ("NAS100_USD", 20000), ("BTC_USD", 60000)):
        print(f"    {sym:<12} {klass(sym):<10} 1:{LEVERAGE[klass(sym)]:<4} "
              f"notional ${notional_usd(sym, pr):>12,.0f}   marge ${margin_per_lot(sym, pr):>10,.0f} per lot")

    # 2019 = klimjaar zonder cryptodata. 2023 = volledig jaar MET crypto (M15
    # crypto begint pas in 2020), dus de enige die 1:2 echt test.
    for year in (2019, 2023):
        for bal in (50_000, 500_000):
            analyse(run(bal, year), bal, f"{year}")
    print("\n[w5_margin_real] DONE_MARKER")


if __name__ == "__main__":
    main()
