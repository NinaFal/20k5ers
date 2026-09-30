#!/usr/bin/env python3
"""
100k account — SCALED avg-annual profit over black-swan-free multi-year spans.

Complements sweep_100k_yearly.py (which does fresh-year cold starts). Here the
account compounds continuously across a clean span so we see the scaled run-rate
(later years sized off a higher funded level). Fresh $100k, CHF pairs excluded,
cap=3, scaling uncapped. Spans avoid 2015 (CHF) and 2020 (COVID).

Run:  uv run python3 backtest/src/sweep_100k_continuous.py
"""
import concurrent.futures, importlib.util, json, os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "sweep_100k_continuous.json"
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

BALANCE = "100000"
CHF = "USD_CHF,EUR_CHF,GBP_CHF,AUD_CHF,NZD_CHF,CAD_CHF,CHF_JPY"
SPANS = [("2016-01-01", "2019-12-31", 4), ("2021-01-01", "2024-12-31", 4)]
RISKS = [1.5, 2.5, 3.5]


def env39():
    data = json.loads((DOE_DIR / "stage5c_oos_screen.json").read_text())
    e = next(dict(r["env"]) for r in data if int(r["trial"]) == 39)
    e.update({"CORR_GROUP_CAP": "3", "FIVEERS_MAX_SCALE": "4000000", "EXCLUDE_SYMBOLS": CHF})
    return e


def ts(): return datetime.now().strftime("%H:%M:%S")


def run(cell):
    start, end, yrs, risk = cell
    tp = dict(scr.TP_OVER); tp["risk_per_trade_pct"] = risk
    r = dh.run_single(env39(), tp, start, end, balance=BALANCE)
    a = dh.extract_attrs(r); fi = (r or {}).get("fail_info") or {}
    o = {"span": f"{start[:4]}-{end[:4]}", "years": yrs, "risk_pct": risk,
         "failed": a.get("failed"), "net": a.get("net"),
         "avg_per_year": round((a.get("net") or 0)/yrs),
         "max_tdd": a.get("max_tdd"), "max_ddd": a.get("max_ddd"),
         "final_funded": a.get("final_funded"), "scalings": a.get("scalings"),
         "breach_type": fi.get("breach_type"), "breach_time": str(fi.get("time") or "")[:10]}
    print(f"[{ts()}] {o['span']} risk={risk}%  {'BREACH' if a.get('failed') else 'ok    '}"
          f"  net=${a.get('net',0):>10,.0f}  avg/yr=${o['avg_per_year']:>9,.0f}"
          f"  funded=${a.get('final_funded',0):>9,}  tdd={a.get('max_tdd',0):.2f}%"
          f"  ddd={a.get('max_ddd',0):.2f}%  {o['breach_type'] or ''} {o['breach_time']}", flush=True)
    return o


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try: done = {(d["span"], d["risk_pct"]): d for d in json.loads(OUT.read_text())}
        except Exception: pass
    cells = [(s, e, y, r) for (s, e, y) in SPANS for r in RISKS
             if (f"{s[:4]}-{e[:4]}", r) not in done]
    print(f"[{ts()}] 100k continuous sweep: {len(cells)} cells", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(run, cells):
            results.append(o); results.sort(key=lambda d: (d["span"], d["risk_pct"]))
            OUT.write_text(json.dumps(results, indent=2, default=str))
    print("\n=== 100k scaled continuous (CHF excl, cap3, uncapped) ===", flush=True)
    print(f"{'span':>10}{'risk':>6}{'result':>8}{'net':>12}{'avg/yr':>11}{'funded':>10}{'TDD%':>7}{'DDD%':>7}", flush=True)
    for d in sorted(results, key=lambda d: (d["span"], d["risk_pct"])):
        print(f"{d['span']:>10}{d['risk_pct']:>6}{'BREACH' if d['failed'] else 'ok':>8}"
              f"{d['net']:>12,.0f}{d['avg_per_year']:>11,.0f}{d['final_funded']:>10,}"
              f"{d['max_tdd']:>7.2f}{d['max_ddd']:>7.2f}", flush=True)
    print("[sweep_100k_continuous] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
