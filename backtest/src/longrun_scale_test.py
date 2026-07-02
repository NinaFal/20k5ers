#!/usr/bin/env python3
"""
Long-run scaling test — how far does the LOCKED config climb the 5ers ladder
over multi-year horizons, with the scaling cap lifted to $1M?

Motivation: the $20K/month income floor is only reachable at a high funded
level (~$1M at this edge).  The $400K cap was NEVER binding in validation (best
7yr window reached only $175K), so the real bottleneck is CLIMB SPEED, not the
ceiling.  This run lifts FIVEERS_MAX_SCALE to $1M and reports, per window:
the full scaling trajectory, final funded level, total withdrawn (real income),
$/month take-home, max TDD, and breach status.

Risk stays regime-adaptive (the locked WINNER_ENV) — nothing is cranked here.
This is a measurement, not an optimization.

Usage:
  python -u backtest/src/longrun_scale_test.py
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import doe_harness as dh
from stage4_validate import WINNER_ENV, WINNER_TP

DOE_DIR = REPO / "backtest" / "output" / "doe"
OUT_JSON = DOE_DIR / "longrun_scale_test.json"
OUT_RPT  = DOE_DIR / "longrun_scale_test_report.txt"

# Cap lifted to $1M so the climb is never artificially frozen.
CAP = os.getenv("LONGRUN_CAP", "1000000")

# Multi-year horizons. Data runs 2015-01 .. 2024-12, so a true 10yr run must
# start in 2015 (known carry-in breach), the rest are clean long horizons.
WINDOWS = [
    ("2015-01-01", "2024-12-31"),   # 10yr — full path
    ("2016-01-01", "2024-12-31"),   # 9yr  — past the 2015 carry-in
    ("2017-01-01", "2024-12-31"),   # 8yr
    ("2018-01-01", "2024-12-31"),   # 7yr — best validation performer
]


def months_between(s, e):
    sy, sm, sd = map(int, s.split("-"))
    ey, em, ed = map(int, e.split("-"))
    return (ey - sy) * 12 + (em - sm) + (ed - sd) / 30.0


def run_window(start, end):
    env = dict(WINNER_ENV)
    env["FIVEERS_MAX_SCALE"] = CAP
    res = dh.run_single(env, WINNER_TP, start, end, balance="50000")
    if res is None:
        return {"start": start, "end": end, "error": "infra_failure"}
    log = res.get("fiveers_scaling_log", []) or []
    funded = res.get("fiveers_final_funded_level", 50000)
    withdrawn = res.get("fiveers_total_withdrawn", 0.0)
    m = months_between(start, end)
    # compact trajectory: list of new levels reached, with date
    traj = [(e["time"][:10], int(e["new_level"])) for e in log
            if e.get("new_level", 0) > e.get("old_level", 0)]
    return {
        "start": start, "end": end, "months": round(m, 1),
        "failed": bool(res.get("account_failed")),
        "breach_type": res.get("breach_type", ""),
        "survived_days": res.get("survived_days"),
        "net_pnl": round(float(res.get("net_pnl") or 0)),
        "max_tdd": round(float(res.get("max_tdd_pct") or 0), 2),
        "max_ddd": round(float(res.get("max_ddd_pct") or 0), 2),
        "scalings": len(log),
        "final_funded": int(funded),
        "withdrawn": round(float(withdrawn)),
        "withdrawn_per_month": round(float(withdrawn) / m) if m else 0,
        "trajectory": traj,
    }


def main():
    results = []
    if OUT_JSON.exists():
        try:
            results = json.loads(OUT_JSON.read_text())
        except Exception:
            results = []
    done = {(r["start"], r["end"]) for r in results if "error" not in r}

    for (s, e) in WINDOWS:
        if (s, e) in done:
            print(f"[skip] {s} -> {e} (done)")
            continue
        print(f"[run]  {s} -> {e}  (cap=${int(CAP):,}) ...", flush=True)
        r = run_window(s, e)
        results.append(r)
        OUT_JSON.write_text(json.dumps(results, indent=2))
        if "error" in r:
            print(f"       ERROR: {r['error']}")
            continue
        status = f"BREACH({r['breach_type']})" if r["failed"] else "ok"
        print(f"       {status}  funded=${r['final_funded']:,}  "
              f"withdrawn=${r['withdrawn']:,} (${r['withdrawn_per_month']:,}/mo)  "
              f"tdd={r['max_tdd']}%  scalings={r['scalings']}", flush=True)

    # report
    lines = ["LONG-RUN SCALING TEST — cap lifted to ${:,}".format(int(CAP)),
             "=" * 78,
             "Locked config, regime-adaptive risk. Measurement only.\n",
             f"{'Window':<24} {'Mo':>4} {'Status':>14} {'Funded':>9} "
             f"{'Withdrawn':>10} {'$/mo':>7} {'TDD':>6} {'Scal':>4}"]
    lines.append("-" * 88)
    for r in results:
        if "error" in r:
            lines.append(f"{r['start']+' -> '+r['end']:<24} ERROR {r['error']}")
            continue
        status = f"BREACH({r['breach_type']})" if r["failed"] else "ok"
        lines.append(
            f"{r['start']+' -> '+r['end']:<24} {r['months']:>4.0f} {status:>14} "
            f"${r['final_funded']:>8,} ${r['withdrawn']:>9,} "
            f"${r['withdrawn_per_month']:>6,} {r['max_tdd']:>5.1f}% {r['scalings']:>4}")
    lines.append("\nScaling trajectories (date → new funded level):")
    for r in results:
        if "error" in r:
            continue
        lines.append(f"\n  {r['start']} -> {r['end']}:")
        if not r["trajectory"]:
            lines.append("    (no scaling events)")
        for (d, lvl) in r["trajectory"]:
            lines.append(f"    {d}  →  ${lvl:,}")
    OUT_RPT.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print("\nLONGRUN_SCALE_TEST_DONE_MARKER")


if __name__ == "__main__":
    main()
