#!/usr/bin/env python3
"""
Hoe duur is de KLIM? 2015 onder vier kostenmodellen.

AANLEIDING. Elf jaar gefund met per-instrument kosten stierf in 2015: ergste dag
6,13% tegen een muur van 5%, win rate 53,1% tegen 59,5% zonder kosten. Dat is de
tegenovergestelde uitkomst van de challengemeting, waar dezelfde kosten precies
één venster van de veertig kostten. Het verschil is blootstelling — 2015 is het
enige KLIMJAAR, met risico per trade rond 3,9% tegen 0,87% op de cap, en het
duurt een jaar in plaats van zestien dagen.

MAAR HET MODEL IS MET OPZET TE DUUR. Het rekent de spread op elke entry EN nog
eens op elke SL-exit. Die tweede is geen spread — die betaal je bij entry al —
maar een slippagebuffer, en in liquide forex is echte stop-slippage doorgaans
onder de halve pip, niet 1,2 tot 4,5. Een uitkomst die alleen bij die dubbele
telling omvalt, valt in werkelijkheid misschien niet om.

Daarom vier armen op hetzelfde jaar, van gratis naar overdreven:

    geen        niets                         (de bestaande referentie)
    entry       spread alleen op de entry     ONDERGRENS — het verdedigbare
                                              minimum: je kruist de spread één
                                              keer, bij openen
    entry_slip  entry + halve pip op stops    REALISTISCH — echte stop-slippage
    vol         entry + volle spread op stops BOVENGRENS — het model dat stierf

Ligt de ergste dag in de arm `entry` ook boven de 5%, dan is het resultaat hard
en is de klim met deze configuratie niet te doen. Blijft hij eronder, dan ligt
de waarheid ertussen en vertelt de reeks hoe gevoelig de klim precies is.

Alleen 2015, want daar valt de beslissing. Een jaar per arm, niet elf.

Draaien:  uv run python3 backtest/src/w5_cost_bracket.py [arm]
          uv run python3 backtest/src/w5_cost_bracket.py --report
"""
import importlib.util, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)
_c = importlib.util.spec_from_file_location("cr", str(HERE / "w5_costs_real.py"))
cr = importlib.util.module_from_spec(_c); _c.loader.exec_module(cr)

YEAR = 2015
OUT = w5.W5_DIR / "cost_bracket.json"
FULL = cr.spread_map(1.0)
# Halve pip op stops voor elk symbool waarvoor een spread bestaat; de entry
# houdt zijn volle spread. Twee aparte knoppen bestaan niet in de simulator, dus
# dit wordt gedraaid als "opslag = het lagere getal" met COST_LIMIT_ENTRIES aan
# en de entry apart verhoogd — zie de opmerking bij ARMS.
ARMS = {
    # `entry`: opslag alleen waar een fill plaatsvindt die de spread kruist.
    # De simulator kent één opslagwaarde per symbool en gebruikt die op BEIDE
    # plekken. Om de SL-exit gratis te maken zet deze arm GAP_FILLS aan (default)
    # en de opslag op nul voor de exit — wat niet kan. Dus: deze arm draait met
    # SLIPPAGE_MAP op de volle spread en COST_LIMIT_ENTRIES=1, maar met
    # SL_SLIPPAGE_OFF=1, een knop die de simulator hiervoor krijgt.
    "entry":      {"SLIPPAGE_MAP": json.dumps(FULL), "COST_LIMIT_ENTRIES": "1",
                   "SL_SLIPPAGE_OFF": "1"},
    "entry_slip": {"SLIPPAGE_MAP": json.dumps(FULL), "COST_LIMIT_ENTRIES": "1",
                   "SL_SLIPPAGE_PIPS": "0.5"},
    "vol":        {"SLIPPAGE_MAP": json.dumps(FULL), "COST_LIMIT_ENTRIES": "1"},
}


def run(arm):
    import shutil, subprocess
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(w5.BASE_ENV)
    e.update(b["env"])
    e["EXCLUDE_SYMBOLS"] = "XRP_USD,ADA_USD,BTC_USD,ETH_USD,XAG_USD,XAU_USD,CAD_JPY,NAS100_USD"
    e["OIL_ENABLE"] = "1"; e["SPX500_ENABLE"] = "0"
    e["FIVEERS_MAX_SCALE"] = "500000"
    e["CFG_DAILY_WALL_PCT"] = "5.0"
    e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    for k in ("SLIPPAGE_MAP", "COST_LIMIT_ENTRIES", "SL_SLIPPAGE_OFF", "SL_SLIPPAGE_PIPS"):
        e.pop(k, None)
    e.update(ARMS[arm])
    d = w5.DOE_DIR / "tmp" / f"brk_{arm}_{YEAR}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", f"{YEAR}-01-01", "--end", f"{YEAR}-12-31",
                        "--balance", "50000.00", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "geen results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        return {"withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
                "final_balance": r.get("final_balance"),
                "funded_level_end": (log[-1]["new_level"] if log else 50000.0),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
                "account_failed": r.get("account_failed"),
                "fail_reason": (r.get("fail_info") or {}).get("reason")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def report():
    store = w5.load_json(OUT)
    ref = json.loads((w5.W5_DIR / "decade_geen_index.json").read_text())["years"]["2015"]
    dead = json.loads((w5.W5_DIR / "decade_geen_index__kosten.json").read_text())["years"]["2015"]
    rows = [("geen", ref), ("entry", store.get("entry")),
            ("entry_slip", store.get("entry_slip")), ("vol", store.get("vol") or dead)]
    print("\n" + "=" * 78)
    print(f"KLIMJAAR {YEAR} — vier kostenmodellen, muur 5% per dag")
    print(f"\n{'arm':12}{'trades':>8}{'win%':>8}{'ergste dag':>12}{'opgenomen':>14}  uitkomst")
    for name, r in rows:
        if not r:
            print(f"{name:12}{'-':>8}{'-':>8}{'-':>12}{'-':>14}  nog niet gedraaid"); continue
        ddd = r.get("max_ddd_pct")
        print(f"{name:12}{str(r.get('trades')):>8}{str(r.get('win_rate')):>8}"
              f"{f'{ddd:.2f}%':>12}${(r.get('withdrawn') or 0):>13,.0f}  "
              + ("DOOD" if r.get("account_failed") else "overleeft"))
    print("\n[w5_cost_bracket] DONE_MARKER", flush=True)


if __name__ == "__main__":
    if "--report" in sys.argv:
        report(); sys.exit()
    arm = sys.argv[1] if len(sys.argv) > 1 else "entry"
    if arm not in ARMS:
        raise SystemExit(f"onbekende arm {arm!r}; kies uit {sorted(ARMS)}")
    print(f"[bracket] {YEAR}, arm {arm}", flush=True)
    r = run(arm)
    store = w5.load_json(OUT); store[arm] = r; w5.atomic_write(OUT, store)
    print(f"[bracket] {arm}: {json.dumps(r)}", flush=True)
    report()
