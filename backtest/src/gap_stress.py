#!/usr/bin/env python3
"""
#7 — Gap / slippage stress sweep.

The live thesis is: on an M1 chart with 5s equity polling, the 3.2% DDD halt
closes positions before the 5% daily limit, so the account "cannot breach
normally." That holds ONLY if exits fill near the trigger. The real risk is a
weekend/news GAP: price reopens far past the stop, every open position closes at
a worse price at once, and the realized loss jumps past 5% in a single tick — no
amount of polling frequency helps once the market has gapped.

This driver quantifies that. It re-runs the bot over a fixed window at
increasing adverse-slippage levels (a proxy for gap severity on fills/SL exits,
on top of the worst-case intrabar close already modelled) and reports the
max DDD, breach count, and survival at each level — i.e. how big a gap it takes
to kill the account.

Usage:
  python3 backtest/src/gap_stress.py
  python3 backtest/src/gap_stress.py --start 2015-01-01 --end 2015-12-31
  python3 backtest/src/gap_stress.py --levels 0,1,2,5,10,20
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"


def run_level(slippage, start, end, balance, terminal):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["SLIPPAGE_PIPS"] = str(slippage)
        env["GAP_FILLS"] = "1"
        env["TERMINAL_ON_BREACH"] = terminal
        cmd = [sys.executable, str(BACKTEST),
               "--start", start, "--end", end,
               "--balance", str(balance), "--output", td]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        rj = Path(td) / "results.json"
        if proc.returncode != 0 or not rj.exists():
            return {"slippage": slippage, "error": proc.returncode}
        d = json.loads(rj.read_text())
        fi = d.get("fail_info") or {}
        return {
            "slippage": slippage,
            "max_ddd": d.get("max_ddd_pct"),
            "breaches": d.get("breaches_5pct"),
            "ddd_halts": d.get("ddd_halts"),
            "failed": bool(d.get("account_failed")),
            "survived_days": fi.get("survived_days"),
            "net_pnl": d.get("net_pnl"),
            "trades": d.get("total_trades"),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2015-12-31")
    ap.add_argument("--balance", type=float, default=50000)
    ap.add_argument("--levels", default="0,0.5,1,2,5,10",
                    help="comma-separated adverse-slippage pip levels (gap proxy)")
    ap.add_argument("--terminal", default="1", help="TERMINAL_ON_BREACH (1=stop at breach)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    levels = [float(x) for x in args.levels.split(",")]
    print(f"Gap stress: {args.start}..{args.end}  balance=${args.balance:,.0f}  "
          f"terminal_on_breach={args.terminal}")
    print("-" * 74)
    print(f"{'slip(pips)':>10} {'maxDDD%':>8} {'breaches':>9} {'ddd_halts':>10} "
          f"{'outcome':>9} {'days':>5} {'netPnL':>12}")
    print("-" * 74)

    results = []
    for lv in levels:
        r = run_level(lv, args.start, args.end, args.balance, args.terminal)
        results.append(r)
        if "error" in r:
            print(f"{lv:>10} ERROR(rc={r['error']})")
            continue
        outcome = "BREACH" if r["failed"] else "ok"
        days = str(r["survived_days"]) if r["failed"] else "-"
        net = r["net_pnl"] or 0
        print(f"{lv:>10} {str(r['max_ddd']):>8} {str(r['breaches']):>9} "
              f"{str(r['ddd_halts']):>10} {outcome:>9} {days:>5} "
              f"{('$%s' % format(int(net), ',')):>12}")

    print("-" * 74)
    first_breach = next((r["slippage"] for r in results
                         if "error" not in r and r["failed"]), None)
    if first_breach is not None:
        print(f"FIRST BREACH at adverse slippage = {first_breach} pips")
    else:
        print("No breach across tested levels.")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"Summary written to {args.out}")


if __name__ == "__main__":
    main()
