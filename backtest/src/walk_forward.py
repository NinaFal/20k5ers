#!/usr/bin/env python3
"""
#6 — Walk-forward / rolling-start robustness driver.

The single 2015->2025 backtest reports ONE path: it happened to scale 50K->125K
before dying on 2015-06-28. That is one draw from a distribution. A strategy
that only survives if you happen to start in a benign month is not robust.

This driver re-runs the SAME bot from a FRESH $50K account at many different
start dates (terminal-on-breach ON) and records, for each start:
  - did the account survive the horizon, or breach?
  - if it breached: how many days did it last, at what funded level?

The output is a survival distribution — "X of N start dates survived" — which is
the honest read on robustness, not the one lucky compounding path.

Usage:
  python3 backtest/src/walk_forward.py
  python3 backtest/src/walk_forward.py --horizon-days 365 --step-months 3
  python3 backtest/src/walk_forward.py --starts 2015-01-01,2018-06-01,2020-01-01

Each window shares the cached M15 data, so only the first window pays the CSV
load cost. Runs are sequential.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"


def month_starts(first: str, last: str, step_months: int):
    y, m, _ = (int(x) for x in first.split("-"))
    ly, lm, _ = (int(x) for x in last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}-01")
        m += step_months
        while m > 12:
            m -= 12
            y += 1
    return out


def run_window(start, horizon_days, balance, slippage, gap_fills):
    end = (datetime.fromisoformat(start) + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["TERMINAL_ON_BREACH"] = "1"
        env["SLIPPAGE_PIPS"] = str(slippage)
        env["GAP_FILLS"] = gap_fills
        cmd = [sys.executable, str(BACKTEST),
               "--start", start, "--end", end,
               "--balance", str(balance), "--output", td]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        rj = Path(td) / "results.json"
        if proc.returncode != 0 or not rj.exists():
            return {"start": start, "error": proc.returncode}
        d = json.loads(rj.read_text())
        fi = d.get("fail_info") or {}
        return {
            "start": start, "end": end,
            "failed": bool(d.get("account_failed")),
            "survived_days": fi.get("survived_days"),
            "funded_at_fail": fi.get("funded_level_at_failure"),
            "max_ddd": d.get("max_ddd_pct"),
            "final_funded": d.get("fiveers_final_funded_level"),
            "withdrawn": d.get("fiveers_total_withdrawn"),
            "trades": d.get("total_trades"),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", default="2015-01-01")
    ap.add_argument("--last", default="2024-01-01")
    ap.add_argument("--step-months", type=int, default=6)
    ap.add_argument("--horizon-days", type=int, default=365)
    ap.add_argument("--balance", type=float, default=50000)
    ap.add_argument("--slippage", type=float, default=0.5)
    ap.add_argument("--gap-fills", default="1")
    ap.add_argument("--starts", default=None,
                    help="comma-separated explicit start dates (overrides first/last/step)")
    ap.add_argument("--out", default=None, help="write JSON summary to this path")
    args = ap.parse_args()

    starts = (args.starts.split(",") if args.starts
              else month_starts(args.first, args.last, args.step_months))

    print(f"Walk-forward: {len(starts)} windows, horizon={args.horizon_days}d, "
          f"slippage={args.slippage}, gap_fills={args.gap_fills}")
    print("-" * 78)
    print(f"{'start':12} {'outcome':9} {'days':>5} {'fail@funded':>12} "
          f"{'finalFunded':>12} {'maxDDD':>7}")
    print("-" * 78)

    results, survived = [], 0
    for s in starts:
        r = run_window(s, args.horizon_days, args.balance, args.slippage, args.gap_fills)
        results.append(r)
        if "error" in r:
            print(f"{s:12} ERROR(rc={r['error']})")
            continue
        if r["failed"]:
            print(f"{s:12} {'BREACH':9} {str(r['survived_days']):>5} "
                  f"{('$%s' % format(int(r['funded_at_fail'] or 0), ',')):>12} "
                  f"{'-':>12} {str(r['max_ddd']):>7}")
        else:
            survived += 1
            ff = int(r["final_funded"] or 0)
            print(f"{s:12} {'SURVIVE':9} {'-':>5} {'-':>12} "
                  f"{('$%s' % format(ff, ',')):>12} {str(r['max_ddd']):>7}")

    print("-" * 78)
    n = sum(1 for r in results if "error" not in r)
    pct = (100.0 * survived / n) if n else 0
    print(f"SURVIVAL: {survived}/{n} windows survived {args.horizon_days} days ({pct:.0f}%)")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"Summary written to {args.out}")


if __name__ == "__main__":
    main()
