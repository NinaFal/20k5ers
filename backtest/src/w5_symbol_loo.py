#!/usr/bin/env python3
"""
Welke tickers erin en welke eruit — LAAT-ER-EEN-WEG, want optellen mag niet.

WAAROM DE BESTAANDE TABEL DE VRAAG NIET BEANTWOORDT. w5_per_symbol telt per
symbool de winst op uit EEN run. Dat is een boekhoudkundige uitsplitsing, geen
beslissingsmaat. De symbolen concurreren namelijk om dezelfde plekken:
MAX_TOTAL_POSITIONS staat op 20, CORR_GROUP_CAP op 6 en de cumulatieve risicocap
op 7%. Haal je een symbool weg, dan verdwijnen zijn trades niet zomaar — een
deel wordt vervangen door trades die eerder werden geweigerd omdat het boek vol
zat. De bijdragen zijn dus NIET optelbaar, en goud, zilver en CAD_JPY zijn er
wel op beoordeeld.

Deze studie meet in plaats daarvan het verschil dat de BESLISSING maakt:

    basis       de volledige configuratie
    -SYMBOOL    dezelfde configuratie, dat ene symbool eruit   (29 armen)
    +SYMBOOL    dezelfde configuratie, dat ene symbool erbij   (8 armen)

Elke arm draait elf jaar gefund vanaf $50.000 op de echte 5ers-ladder, met
doorgerolde balans, zodat elk jaar even lang duurt. Een breach beeindigt het
account en de resterende jaren worden niet gedraaid — dat IS de uitkomst.

WAAROM MET KOSTEN EN MET DE KANDIDAAT. Zonder kosten meet je een wereld die niet
bestaat: de entry-spread bleek het klimjaar te doden. En met de HUIDIGE
configuratie sterft elke arm in 2015, dus er valt niets te vergelijken. Deze
studie draait daarom op de survival-kandidaat plus per-instrument kosten — de
configuratie die we zouden handelen. Dat maakt de uitkomst VOORWAARDELIJK: hij
geldt zolang die kandidaat de bevestiging op de achtergehouden vensters haalt.

DE BESLISREGEL, lexicografisch, in deze volgorde:
    1  het account overleeft alle elf jaar          harde eis
    2  minste breaches op de challenge-vensters     (aparte stap, zie hieronder)
    3  meeste opgenomen winst
    4  win-rate wordt gerapporteerd, niet op gestuurd

Punt 4 is geen slordigheid. NAS100 won 61,6% van zijn trades en verloor geld:
gemiddelde winst $329 tegen gemiddeld verlies -$731, profit factor 0,72 over 164
trades. Sturen op win-rate had hem laten staan.

WAT DIT NIET IS. Elf jaar is de data waarop deze configuratie is afgesteld. De
beste symboollijst uitzoeken op diezelfde elf jaar is precies hoe je overfit.
Wat hieruit komt is een KANDIDAATLIJST die dezelfde behandeling verdient als de
survival-kandidaat: bevestigen op vensters die niet zijn meegewogen. De
challenge-stap (punt 2) is bewust een aparte run op een aparte vensterlijst.

Draaien:  uv run python3 backtest/src/w5_symbol_loo.py <arm>
          uv run python3 backtest/src/w5_symbol_loo.py --armen
          uv run python3 backtest/src/w5_symbol_loo.py --report
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)
_cc = importlib.util.spec_from_file_location("cc", str(HERE / "w5_confirm_candidate.py"))
cc = importlib.util.module_from_spec(_cc); _cc.loader.exec_module(cc)
_cr = importlib.util.spec_from_file_location("cr", str(HERE / "w5_costs_real.py"))
cr = importlib.util.module_from_spec(_cr); _cr.loader.exec_module(cr)

YEARS = list(range(2015, 2026))
START_BALANCE = 50_000.0
TRIAL = int(os.getenv("W5_CAND_TRIAL", "31"))
OUT = w5.W5_DIR / "symbol_loo.json"
COSTS = {"SLIPPAGE_MAP": json.dumps(cr.spread_map(1.0)), "COST_LIMIT_ENTRIES": "1"}

BASE_EXCL = [s.strip() for s in w5.BASE_ENV["EXCLUDE_SYMBOLS"].split(",") if s.strip()]
# De 29 die nu meedoen, uit config.py zodat de lijst niet twee keer bestaat.
def _universe():
    env = dict(os.environ)
    env["SPX500_ENABLE"] = "0"
    out = subprocess.run(
        [sys.executable, "-c",
         "import config,json;print(json.dumps(config.all_market_instruments()))"],
        env=env, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True)
    alle = json.loads(out.stdout.strip().splitlines()[-1])
    return [s for s in alle if s not in BASE_EXCL]

AAN = _universe()
# XBR en XTI hangen aan OIL_ENABLE, niet aan de uitsluitingslijst; ze krijgen
# hun eigen armen zodat ze wel meetbaar zijn.
UIT = [s for s in BASE_EXCL if s not in ("XRP_USD", "ADA_USD")]   # 5ers biedt die twee niet aan

ARMS = {"basis": (BASE_EXCL, True)}
for s in AAN:
    if s in ("XBR_USD", "XTI_USD"):
        continue
    ARMS[f"-{s}"] = (BASE_EXCL + [s], True)
ARMS["-XBR_USD"] = (BASE_EXCL + ["XBR_USD"], True)
ARMS["-XTI_USD"] = (BASE_EXCL + ["XTI_USD"], True)
ARMS["-OLIE"] = (BASE_EXCL, False)                 # allebei de olies eruit
for s in UIT:
    ARMS[f"+{s}"] = ([x for x in BASE_EXCL if x != s], True)


def run_year(arm, year, balance):
    excl, oil = ARMS[arm]
    env, tp = cc.candidate(TRIAL)[:2]
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(env)
    e["EXCLUDE_SYMBOLS"] = ",".join(excl)
    e["OIL_ENABLE"] = "1" if oil else "0"
    e["SPX500_ENABLE"] = "0"
    e["FIVEERS_MAX_SCALE"] = "500000"; e["CFG_DAILY_WALL_PCT"] = "5.0"
    e.setdefault("BROKER_TYPE", "fiveers_live")
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp}); e["PYTHONUTF8"] = "1"
    for k in ("SLIPPAGE_MAP", "COST_LIMIT_ENTRIES", "SL_SLIPPAGE_OFF", "SL_SLIPPAGE_PIPS"):
        e.pop(k, None)
    e.update(COSTS)
    # De arm MOET in de padnaam, anders wissen gelijktijdige armen elkaars
    # werkmap halverwege (zie W5_DATA_INTEGRITY.md).
    d = w5.DOE_DIR / "tmp" / f"loo_{arm.replace('/', '_')}_{year}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", f"{year}-01-01", "--end", f"{year}-12-31",
                        "--balance", f"{balance:.2f}", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "geen results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        return {"withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
                "final_balance": r.get("final_balance"),
                "funded_level_end": (log[-1]["new_level"] if log else balance),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
                "account_failed": r.get("account_failed"),
                "fail_reason": (r.get("fail_info") or {}).get("reason")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_arm(arm):
    bal = START_BALANCE
    for y in YEARS:
        store = w5.load_json(OUT)
        slot = store.setdefault(arm, {"years": {}})
        if slot.get("dood"):
            return
        if str(y) in slot["years"]:
            r = slot["years"][str(y)]
            if r.get("error") or r.get("account_failed"):
                return
            bal = r.get("funded_level_end") or bal
            continue
        r = run_year(arm, y, bal)
        store = w5.load_json(OUT); slot = store.setdefault(arm, {"years": {}})
        slot["years"][str(y)] = r
        if r.get("account_failed"):
            slot["dood"] = {"jaar": y, "reden": r.get("fail_reason")}
        w5.atomic_write(OUT, store)
        if r.get("error"):
            print(f"[loo] {arm} {y}: FOUT {r['error']}", flush=True); return
        print(f"[loo] {arm} {y}: opgenomen ${r['withdrawn']:,.0f} "
              f"lvl ${(r.get('funded_level_end') or 0):,.0f} DDD {r['max_ddd_pct']}%"
              + (f"  <-- DOOD: {r['fail_reason']}" if r.get("account_failed") else ""),
              flush=True)
        if r.get("account_failed"):
            return
        bal = r.get("funded_level_end") or bal


def samenvat(arm, store):
    slot = store.get(arm) or {}
    ys = [v for v in slot.get("years", {}).values() if not v.get("error")]
    if not ys:
        return None
    return {"jaren": len(ys), "dood": bool(slot.get("dood")),
            "dood_jaar": (slot.get("dood") or {}).get("jaar"),
            "opgenomen": sum(v.get("withdrawn") or 0 for v in ys),
            "ergste_dag": max(v.get("max_ddd_pct") or 0 for v in ys),
            "ergste_totaal": max(v.get("max_tdd_pct") or 0 for v in ys),
            "trades": sum(v.get("trades") or 0 for v in ys),
            "win": (sum((v.get("win_rate") or 0) * (v.get("trades") or 0) for v in ys)
                    / max(sum(v.get("trades") or 0 for v in ys), 1))}


def report():
    store = w5.load_json(OUT)
    b = samenvat("basis", store)
    print("\n" + "=" * 96)
    print(f"LAAT-ER-EEN-WEG — elf jaar gefund, kandidaat trial {TRIAL}, met per-instrument kosten")
    if not b:
        print("\n  de basisarm is nog niet af; zonder die referentie zegt geen enkel verschil iets")
        print("\n[w5_symbol_loo] DONE_MARKER", flush=True); return
    print(f"\nBASIS: {b['jaren']}/11 jaar, ${b['opgenomen']:,.0f} opgenomen, "
          f"ergste dag {b['ergste_dag']:.2f}%, {b['trades']} trades, win {b['win']:.1f}%"
          + ("  DOOD" if b["dood"] else "  overleeft"))
    rows = []
    for arm in ARMS:
        if arm == "basis":
            continue
        s = samenvat(arm, store)
        if not s or s["jaren"] < 11 and not s["dood"]:
            continue                                  # nog niet af
        rows.append((s["opgenomen"] - b["opgenomen"], arm, s))
    if not rows:
        print("\n  nog geen afgeronde armen"); print("\n[w5_symbol_loo] DONE_MARKER", flush=True); return
    rows.sort(reverse=True)
    print(f"\n{'arm':16}{'delta winst':>14}{'opgenomen':>14}{'jaren':>7}"
          f"{'ergste dag':>12}{'win%':>7}  oordeel")
    for d, arm, s in rows:
        # Lexicografisch: doodgaan is diskwalificerend, ongeacht de winst.
        if s["dood"]:
            oordeel = f"AFGEVALLEN — dood in {s['dood_jaar']}"
        elif d > 0:
            oordeel = "zonder dit symbool BETER — kandidaat om te schrappen" if arm.startswith("-") \
                      else "met dit symbool BETER — kandidaat om terug te zetten"
        else:
            oordeel = "houden zoals het is"
        print(f"{arm:16}{d:>+14,.0f}{s['opgenomen']:>14,.0f}{s['jaren']:>7}"
              f"{s['ergste_dag']:>11.2f}%{s['win']:>7.1f}  {oordeel}")
    print("\n[w5_symbol_loo] DONE_MARKER", flush=True)


if __name__ == "__main__":
    if "--armen" in sys.argv:
        print("\n".join(ARMS)); sys.exit()
    if "--report" in sys.argv:
        report(); sys.exit()
    arm = sys.argv[1] if len(sys.argv) > 1 else "basis"
    if arm not in ARMS:
        raise SystemExit(f"onbekende arm {arm!r}; zie --armen")
    print(f"[loo] arm {arm}: uitsluitingen={','.join(ARMS[arm][0])} olie={ARMS[arm][1]}", flush=True)
    run_arm(arm)
    report()
