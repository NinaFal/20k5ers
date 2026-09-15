#!/usr/bin/env python3
"""
100k account — max profit per year without breaching, BLACK SWANS EXCLUDED.

Goal: on a fresh $100k funded account (2-step challenge assumed passed), find the
setting that makes the most profit without breaching, leaving real black-swan
events (2015 CHF/SNB unpeg, 2020 COVID) out of the equation.

How black swans are removed:
  - CHF pairs excluded via EXCLUDE_SYMBOLS (kills the 2015-01-15 SNB cliff), and
  - the 2015 and 2020 calendar years are simply not tested.

Design: cold-start a FRESH $100k account on Jan 1 of each clean year and run to
Dec 31 — this is the "year-1 from a fresh 100k" number for each regime. Sweeps
base risk-per-trade. Skeleton = the t39/cap=3 winner (regime mults + ladder),
CORR_GROUP_CAP=3, scaling cap lifted. Resumable (per-cell JSON).

Run:  uv run python3 backtest/src/sweep_100k_yearly.py
"""
import concurrent.futures
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOE_DIR = REPO / "backtest" / "output" / "doe"
OUT = DOE_DIR / "sweep_100k_yearly.json"

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)

os.environ.setdefault("RUN_TIMEOUT_S", "999999")

BALANCE = "100000"
CHF_PAIRS = "USD_CHF,EUR_CHF,GBP_CHF,AUD_CHF,NZD_CHF,CAD_CHF,CHF_JPY"
CLEAN_YEARS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]   # skip 2015 CHF, 2020 COVID
RISK_LEVELS = [1.5, 2.5, 3.5, 5.0]


def t39_env():
    data = json.loads((DOE_DIR / "stage5c_oos_screen.json").read_text())
    env = next(dict(r["env"]) for r in data if int(r["trial"]) == 39)
    env["CORR_GROUP_CAP"] = "3"
    env["FIVEERS_MAX_SCALE"] = "4000000"
    env["EXCLUDE_SYMBOLS"] = CHF_PAIRS
    return env


def ts():
    return datetime.now().strftime("%H:%M:%S")


def run_cell(risk, year):
    env = t39_env()
    tp = dict(scr.TP_OVER); tp["risk_per_trade_pct"] = risk
    r = dh.run_single(env, tp, f"{year}-01-01", f"{year}-12-31", balance=BALANCE)
    a = dh.extract_attrs(r)
    fi = (r or {}).get("fail_info") or {}
    out = {"risk_pct": risk, "year": year, "failed": a.get("failed"),
           "net": a.get("net"), "max_tdd": a.get("max_tdd"), "max_ddd": a.get("max_ddd"),
           "final_funded": a.get("final_funded"), "scalings": a.get("scalings"),
           "trades": a.get("trades"), "breach_type": fi.get("breach_type"),
           "breach_time": str(fi.get("time") or "")[:10]}
    print(f"[{ts()}] risk={risk:>4}% {year}  {'BREACH' if a.get('failed') else 'ok    '}"
          f"  net=${a.get('net',0):>9,.0f}  tdd={a.get('max_tdd',0):5.2f}%"
          f"  ddd={a.get('max_ddd',0):5.2f}%  funded=${a.get('final_funded',0):>9,}"
          f"  {out['breach_type'] or ''} {out['breach_time']}", flush=True)
    return out


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try:
            done = {(d["risk_pct"], d["year"]): d for d in json.loads(OUT.read_text())}
        except Exception:
            pass
    cells = [(r, y) for r in RISK_LEVELS for y in CLEAN_YEARS if (r, y) not in done]
    print(f"[{ts()}] 100k yearly sweep (CHF excl, cap3, uncapped): {len(cells)} cells", flush=True)

    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(run_cell, r, y): (r, y) for (r, y) in cells}
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())
            results.sort(key=lambda d: (d["risk_pct"], d["year"]))
            OUT.write_text(json.dumps(results, indent=2, default=str))

    # Summary matrix: avg/median/min net per risk, breach count, target hit-rate.
    print("\n=== 100k fresh-year profit vs base risk (CHF excl, 2015 & 2020 skipped) ===", flush=True)
    print(f"{'risk%':>6}{'yrs':>5}{'breaches':>9}{'minNet':>11}{'medNet':>11}"
          f"{'avgNet':>11}{'maxNet':>11}{'>=500k':>8}", flush=True)
    for risk in RISK_LEVELS:
        rows = [d for d in results if d["risk_pct"] == risk]
        if not rows:
            continue
        nets = sorted(d["net"] for d in rows)
        br = sum(1 for d in rows if d["failed"])
        med = nets[len(nets)//2]
        avg = sum(nets)/len(nets)
        hit = sum(1 for d in rows if (d["net"] or 0) >= 500000 and not d["failed"])
        print(f"{risk:>6}{len(rows):>5}{br:>9}{nets[0]:>11,.0f}{med:>11,.0f}"
              f"{avg:>11,.0f}{nets[-1]:>11,.0f}{hit:>6}/{len(rows)}", flush=True)
    print("[sweep_100k_yearly] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
