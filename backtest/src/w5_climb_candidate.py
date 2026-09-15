#!/usr/bin/env python3
"""
Het klimjaar 2015 met de survival-kandidaat, met en zonder kosten.

WAAROM DIT DE BESLISSENDE RUN IS. Twee onafhankelijke metingen wijzen dezelfde
kant op. De kostenmeting: met realistische entry-spreads sterft het gefunde
klimjaar — ergste dag 6,13% tegen een muur van 5%, win rate 53,1% tegen 59,5%.
De survival-optimizer: de top vijf van 46 trials zit allemaal op 1,6-1,8% risico
per trade tegen 2,7% nu, en vindt daarmee 1 breach in plaats van 7 op dezelfde
dertig vensters.

Kleiner handelen is precies wat een dunne marge boven de kosten vraagt. Maar dat
is een REDENERING, en die is hier niets waard — beide metingen zijn op iets
anders gedaan. De survival-trials draaiden zonder kosten, en de kostenmeting
draaide op de huidige configuratie. Dit is de eerste run waarin de twee elkaar
ontmoeten.

VIER ARMEN, 2015, elk vanaf $50.000 op de echte ladder:

    nu            huidige configuratie, geen kosten   (referentie: 4,76%, leeft)
    nu_kosten     huidige configuratie, met kosten    (gemeten: 6,13%, DOOD)
    kand          kandidaat, geen kosten              -> wat kost kleiner handelen
    kand_kosten   kandidaat, met kosten               -> de vraag die telt

Als `kand_kosten` onder de 5% blijft is er een pad naar een gefund account dat
de kosten overleeft. Blijft hij erboven, dan is het probleem niet het risico per
trade en moet het ergens anders vandaan komen.

WAT DIT NIET IS. Eén jaar, één pad. De kandidaat is bovendien de beste van 46
trials op een case-enriched screen en nog niet bevestigd op de achtergehouden
vensters. Dit is een richtingaanwijzer, geen bewijs.

Draaien:  uv run python3 backtest/src/w5_climb_candidate.py [arm]
          uv run python3 backtest/src/w5_climb_candidate.py --report
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

YEAR = 2015
TRIAL = int(os.getenv("W5_CAND_TRIAL", "31"))
OUT = w5.W5_DIR / "climb_candidate.json"
COSTS = {"SLIPPAGE_MAP": json.dumps(cr.spread_map(1.0)), "COST_LIMIT_ENTRIES": "1"}
ARMS = {"nu": (False, False), "nu_kosten": (False, True),
        "kand": (True, False), "kand_kosten": (True, True)}


def run(arm):
    use_cand, use_costs = ARMS[arm]
    env, tp = (cc.candidate(TRIAL)[:2] if use_cand else cc.frozen())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(env)
    e["EXCLUDE_SYMBOLS"] = w5.BASE_ENV["EXCLUDE_SYMBOLS"]
    e["OIL_ENABLE"] = "1"; e["SPX500_ENABLE"] = "0"
    e["FIVEERS_MAX_SCALE"] = "500000"; e["CFG_DAILY_WALL_PCT"] = "5.0"
    e.setdefault("BROKER_TYPE", "fiveers_live")
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp}); e["PYTHONUTF8"] = "1"
    for k in ("SLIPPAGE_MAP", "COST_LIMIT_ENTRIES", "SL_SLIPPAGE_OFF", "SL_SLIPPAGE_PIPS"):
        e.pop(k, None)
    if use_costs:
        e.update(COSTS)
    d = w5.DOE_DIR / "tmp" / f"climb_{arm}"
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
                "scale_ups": len(log), "trades": r.get("total_trades"),
                "win_rate": r.get("win_rate"), "max_ddd_pct": r.get("max_ddd_pct"),
                "max_tdd_pct": r.get("max_tdd_pct"),
                "account_failed": r.get("account_failed"),
                "fail_reason": (r.get("fail_info") or {}).get("reason")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def report():
    st = w5.load_json(OUT)
    print("\n" + "=" * 82)
    print(f"KLIMJAAR {YEAR} — huidige configuratie tegen survival-kandidaat (trial {TRIAL})")
    print(f"\n{'arm':14}{'trades':>8}{'win%':>7}{'ergste dag':>12}{'niveau eind':>14}"
          f"{'opgenomen':>13}  uitkomst")
    for a in ARMS:
        r = st.get(a)
        if not r or r.get("error"):
            print(f"{a:14}{'-':>8}{'-':>7}{'-':>12}{'-':>14}{'-':>13}  "
                  + (r["error"] if r else "nog niet gedraaid")); continue
        ddd = "%.2f%%" % (r.get("max_ddd_pct") or 0)
        lvl = r.get("funded_level_end") or 0
        wd = r.get("withdrawn") or 0
        staat = "DOOD" if r.get("account_failed") else "leeft"
        print(f"{a:14}{str(r['trades']):>8}{str(r['win_rate']):>7}{ddd:>12}"
              f"${lvl:>13,.0f}${wd:>12,.0f}  {staat}")
    print("\n[w5_climb_candidate] DONE_MARKER", flush=True)


if __name__ == "__main__":
    if "--report" in sys.argv:
        report(); sys.exit()
    arm = sys.argv[1] if len(sys.argv) > 1 else "kand_kosten"
    if arm not in ARMS:
        raise SystemExit(f"onbekende arm {arm!r}; kies uit {sorted(ARMS)}")
    print(f"[klim] {YEAR}, arm {arm}, trial {TRIAL}", flush=True)
    r = run(arm)
    st = w5.load_json(OUT); st[arm] = r; w5.atomic_write(OUT, st)
    print(f"[klim] {arm}: {json.dumps(r)}", flush=True)
    report()
