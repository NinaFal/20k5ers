#!/usr/bin/env python3
"""
How much profit can the t39 @ cap=3 winner make with more risk + uncapped scaling?

t39's locked config is very safe (peak DDD 3.23%) but conservative — it tops out
at the 400k funded level because its 1.0% base risk never earns enough to scale
past it. This sweeps the BASE risk-per-trade up (keeping t39's regime mults,
drawdown ladder and CORR_GROUP_CAP=3, with the 400k scaling cap LIFTED) to see
how far the account compounds and where the walls start to break.

Each level runs the full 2015-2024 continuous window. Resumable (per-level JSON).
Run under uv:  uv run python3 backtest/src/diag_t39_risk_sweep.py
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
OUT = DOE_DIR / "t39_risk_sweep.json"

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)

os.environ.setdefault("RUN_TIMEOUT_S", "999999")
FULL = ("2015-01-01", "2024-12-31")
RISK_LEVELS = [1.0, 1.5, 2.0, 2.5, 3.0]     # base risk_per_trade_pct


def t39_env():
    data = json.loads((DOE_DIR / "stage5c_oos_screen.json").read_text())
    env = next(dict(r["env"]) for r in data if int(r["trial"]) == 39)
    env["CORR_GROUP_CAP"] = "3"
    env["FIVEERS_MAX_SCALE"] = "4000000"    # lift the 400k scaling cap
    return env


def ts():
    return datetime.now().strftime("%H:%M:%S")


def run_level(risk):
    env = t39_env()
    tp = dict(scr.TP_OVER); tp["risk_per_trade_pct"] = risk
    r = dh.run_single(env, tp, *FULL)
    a = dh.extract_attrs(r)
    fi = (r or {}).get("fail_info") or {}
    out = {
        "risk_pct": risk,
        "failed": a.get("failed"),
        "net": a.get("net"),
        "max_tdd": a.get("max_tdd"),
        "max_ddd": a.get("max_ddd"),
        "final_funded": a.get("final_funded"),
        "scalings": a.get("scalings"),
        "withdrawn": a.get("withdrawn"),
        "breach_type": fi.get("breach_type"),
        "breach_time": fi.get("time"),
    }
    print(f"[{ts()}] risk={risk:>3}%  {'BREACH' if a.get('failed') else 'ok    '}"
          f"  net=${a.get('net',0):>11,.0f}  tdd={a.get('max_tdd',0):.2f}%"
          f"  ddd={a.get('max_ddd',0):.2f}%  funded=${a.get('final_funded',0):>9,}"
          f"  {fi.get('breach_type') or ''} {str(fi.get('time') or '')[:10]}", flush=True)
    return out


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try:
            done = {d["risk_pct"]: d for d in json.loads(OUT.read_text())}
        except Exception:
            pass
    todo = [r for r in RISK_LEVELS if r not in done]
    print(f"[{ts()}] t39 risk sweep — {len(todo)} levels to run: {todo}", flush=True)

    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(run_level, r): r for r in todo}
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())
            results.sort(key=lambda d: d["risk_pct"])
            OUT.write_text(json.dumps(results, indent=2, default=str))

    print("\n=== t39 @ cap=3, scaling UNCAPPED — profit vs base risk ===", flush=True)
    print(f"{'risk%':>6}{'result':>9}{'net':>13}{'TDD%':>7}{'DDD%':>7}"
          f"{'funded':>11}{'scal':>5}  breach", flush=True)
    for d in sorted(results, key=lambda d: d["risk_pct"]):
        print(f"{d['risk_pct']:>6}{'BREACH' if d['failed'] else 'PASS':>9}"
              f"{d['net']:>13,.0f}{d['max_tdd']:>7.2f}{d['max_ddd']:>7.2f}"
              f"{d['final_funded']:>11,}{d['scalings']:>5}"
              f"  {d['breach_type'] or '-'} {str(d['breach_time'] or '')[:10]}", flush=True)
    print("[t39_risk_sweep] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
