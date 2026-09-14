#!/usr/bin/env python3
"""
Kostenrealisme PER INSTRUMENT — de eerlijke versie van w5_costs.py.

w5_costs.py draait een VLAKKE opslag in pips over alle symbolen. Dat is een
gevoeligheidscurve, geen kostenmodel: 1 pip op EUR/USD is ongeveer $10 per lot,
1 pip op Brent is $1 per lot en 1 punt op UK100 is $1 per lot. Gelijk opslaan
betekent dus per symbool een heel ander bedrag, en de curve zegt niets over de
vraag die telt: overleeft dit de kosten die 5ers echt rekent?

Bovendien onderschat de simulator de kosten op een tweede manier. LIMIT-entries
vullen frictieloos op de limietprijs. In werkelijkheid vult een buy limit op de
ASK, dus de trigger ligt een spread te optimistisch. Bijna elke entry van deze
bot is een golden-pocket Fib LIMIT — de plek waar de kosten dus zitten. Deze
run zet COST_LIMIT_ENTRIES=1 en rekent de spread daar wél.

DE SPREADS. Schattingen van typische 5ers/MT5-spreads, niet gemeten aan hun
feed — die hebben we hier niet. Ze zijn met opzet aan de RUIME kant gekozen:
liever een te dure test doorstaan dan een te goedkope.

    majors            1,2 pip     EUR/USD, GBP/USD, USD/JPY, USD/CHF,
                                  USD/CAD, AUD/USD, NZD/USD
    rustige crosses   2,0 pip     EUR/GBP, EUR/CHF, AUD/CAD, NZD/CAD, ...
    JPY-crosses       2,5 pip     EUR/JPY, GBP/JPY, AUD/JPY, CHF/JPY
    dure crosses      4,5 pip     GBP/NZD, GBP/AUD, EUR/NZD, GBP/CAD
    UK100             2,0 punt
    Brent, WTI        4,0 cent

Deze opslag geldt op ELKE entry-fill (limit inbegrepen) en op ELKE SL-exit.
Dat is een dubbele telling ten opzichte van de werkelijkheid, waar je de spread
één keer betaalt: de SL-exit betaalt hem hier een tweede keer. Bewust — het is
tegelijk de slippage-buffer op stops, waar slippage echt bestaat.

HOE DE LIMIET-KOSTEN ZIJN GEMODELLEERD, en waar dat afwijkt van de echte
markt. Echt: een buy limit op X vult pas als de ASK X raakt, dus als de BID op
X - spread staat. De vulprijs is X, maar er zijn MINDER fills. Hier: de trigger
blijft gelijk en de VULPRIJS wordt X + spread. In geld is dat dezelfde spread,
maar de verzameling trades verschilt — dit model handelt evenveel keer en
betaalt per trade, het echte model handelt minder vaak en betaalt niet per
trade. Deze kant is gekozen omdat hij de triggerlogica van de bot niet raakt.

Bijwerking die je in de uitkomst terugziet: een slechtere entry vergroot de
afstand tot de SL, dus de lotgrootte bij hetzelfde risicopercentage KRIMPT, en
de R-doelen schuiven mee. Het pad loopt daardoor chaotisch uiteen — op een kort
venster kan de dure arm toevallig hoger uitkomen. Alleen het gemiddelde over
alle 40 vensters zegt iets.

ARMEN
    base    geen opslag (referentie, identiek aan de bestaande resultaten)
    real    de tabel hierboven
    real2x  alles maal twee — breekt het pas dan, dan is de marge ruim

Draaien:  uv run python3 backtest/src/w5_costs_real.py [arm]
"""
import importlib.util, json, math, os, random, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

SEED = 20260914
N = 40
OUT = w5.W5_DIR / "cost_real.json"

MAJORS   = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
JPY      = ["EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"]
EXPENSIVE = ["GBPNZD", "GBPAUD", "EURNZD", "GBPCAD", "EURAUD"]
QUIET    = ["EURGBP", "EURCHF", "EURCAD", "GBPCHF", "AUDCAD", "AUDNZD",
            "AUDCHF", "NZDCAD", "NZDCHF", "CADCHF"]

def spread_map(mult=1.0):
    m = {}
    for s in MAJORS:    m[s] = 1.2 * mult
    for s in JPY:       m[s] = 2.5 * mult
    for s in EXPENSIVE: m[s] = 4.5 * mult
    for s in QUIET:     m[s] = 2.0 * mult
    m["UK100"] = 2.0 * mult
    m["XBR"]   = 4.0 * mult
    m["XTI"]   = 4.0 * mult
    # Uitgesloten maar hier voor de volledigheid, mocht iemand ze terugzetten.
    m["XAU"] = 3.0 * mult
    m["XAG"] = 3.0 * mult
    m["NAS100"] = 3.0 * mult
    m["US500"] = 1.5 * mult
    m["SPX500"] = 1.5 * mult
    return {k: round(v, 2) for k, v in m.items()}

ARMS = {
    "base":   {},
    "real":   {"SLIPPAGE_MAP": json.dumps(spread_map(1.0)), "COST_LIMIT_ENTRIES": "1"},
    "real2x": {"SLIPPAGE_MAP": json.dumps(spread_map(2.0)), "COST_LIMIT_ENTRIES": "1"},
}


def main():
    arm = sys.argv[1] if len(sys.argv) > 1 else "real"
    if arm not in ARMS:
        raise SystemExit(f"onbekende arm {arm!r}; kies uit {list(ARMS)}")
    rng = random.Random(SEED)
    starts = sorted(rng.sample(w5.CANON, N))

    env = dict(w5.BASE_ENV)
    env.update(json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())["env"])
    env.update(ARMS[arm])
    tp = dict(w5.BASE_TP)
    tp.update(json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())["tp"])

    print(f"[kosten] arm={arm} n={N}")
    if ARMS[arm]:
        print(f"[kosten] opslag: {ARMS[arm]['SLIPPAGE_MAP'][:160]}...")

    store = w5.load_json(OUT)
    mine = store.setdefault(arm, {})
    todo = [s for s in starts if s not in mine]
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        chunk = max(2, w5.WORKERS)
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                mine[futs[f]] = r
            w5.atomic_write(OUT, store)
            done = len(mine)
            br = sum(1 for v in mine.values() if v.get("breach"))
            ps = sum(1 for v in mine.values() if v.get("total"))
            print(f"[kosten] {arm} {done}/{N}  pass={ps} breach={br}", flush=True)

    rows = [mine[s] for s in starts]
    br = sum(1 for r in rows if r["breach"])
    st = sum(1 for r in rows if not r["breach"] and r.get("total") is None)
    tot = sorted(r["total"] for r in rows if r.get("total"))
    print(f"\nARM {arm}: pass {len(tot)}/{N}  breach {br}  stall {st}  "
          f"mediaan {tot[len(tot)//2] if tot else None}d")


def _sum(d, starts):
    rows = [d[s] for s in starts if s in d]
    br = sum(1 for r in rows if r["breach"])
    tot = sorted(r["total"] for r in rows if r.get("total"))
    return {"n": len(rows), "pass": len(tot), "breach": br,
            "stall": len(rows) - br - len(tot),
            "median": tot[len(tot) // 2] if tot else None,
            "le30": sum(1 for t in tot if t <= 30)}


def mcnemar_exact(b, c):
    """Tweezijdige exacte tekentoets op de discordante paren. Alleen de vensters
    waar de armen VAN ELKAAR VERSCHILLEN dragen bij; de rest zegt niets over
    welke arm beter is. Met b+c klein is de normale benadering waardeloos."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def compare():
    """Gepaard, op dezelfde vensters. Ongepaard vergelijken van twee armen die
    toevallig verschillende vensters af hebben is de fout die eerder in dit
    project 3 tegen 1 breaches liet zien waar er niets stond."""
    store = w5.load_json(OUT)
    starts = sorted(random.Random(SEED).sample(w5.CANON, N))
    have = [a for a in ("base", "real", "real2x") if store.get(a)]
    if "base" not in have:
        print("[kosten] geen referentiearm — vergelijken kan niet"); return
    base = store["base"]
    for arm in have:
        if arm == "base":
            continue
        shared = [s for s in starts if s in base and s in store[arm]]
        sb, sa = _sum(base, shared), _sum(store[arm], shared)
        print("\n" + "=" * 66)
        print(f"{arm.upper()} tegen BASE — {len(shared)} GEPAARDE vensters")
        print(f"\n{'':14}{'geen kosten':>14}{arm:>14}{'verschil':>12}")
        for lbl, k in (("geslaagd", "pass"), ("breach", "breach"),
                       ("vastgelopen", "stall"), ("<=30 dagen", "le30"),
                       ("mediaan (d)", "median")):
            a_, b_ = sb[k], sa[k]
            dv = (b_ - a_) if (isinstance(a_, int) and isinstance(b_, int)) else ""
            print(f"{lbl:14}{str(a_):>14}{str(b_):>14}{str(dv):>12}")
        b = sum(1 for s in shared if base[s]["breach"] and not store[arm][s]["breach"])
        c = sum(1 for s in shared if store[arm][s]["breach"] and not base[s]["breach"])
        both = sum(1 for s in shared if base[s]["breach"] and store[arm][s]["breach"])
        print(f"\ngepaarde breach-tabel: beide {both} | alleen base {b} | alleen {arm} {c}")
        print(f"McNemar exact, tweezijdig: p = {mcnemar_exact(b, c):.3f}")
        d = [store[arm][s]["total"] - base[s]["total"] for s in shared
             if base[s].get("total") and store[arm][s].get("total")]
        if d:
            d.sort()
            print(f"dagen per venster (alleen waar beide slagen, n={len(d)}): "
                  f"mediaan {d[len(d)//2]:+d}, slechtste {d[-1]:+d}, beste {d[0]:+d}")
    print("\n[w5_costs_real] DONE_MARKER", flush=True)


if __name__ == "__main__":
    if "--compare" in sys.argv:
        compare()
    else:
        main()
