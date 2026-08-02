#!/usr/bin/env python3
"""
E6 — decade run in resumable YEARLY chunks (Summer Edition, funded, $175k cap).

Why chunked. E5's tenyear arm is a single multi-hour subprocess, and this
container restarts every few minutes — it can never finish. Chunking into
one-year segments that each cache on completion makes the decade measurable:
a restart costs at most the year in flight.

Carry-forward: each year starts at the previous year's closing balance and
funded level, so the P&L path and the 5ers scaling ladder are continuous.

CAVEAT, stated plainly because it matters for interpretation:
  * DAILY drawdown (the 3% wall) is measured within a day, so chunking does not
    affect it — those numbers are exact.
  * TOTAL drawdown (the 10% wall) is measured against a peak the engine tracks
    from the start of ITS run. Chunking resets that baseline each year, so a
    slow multi-year bleed that would breach the total wall can be missed. This
    arm therefore UNDER-detects total-wall breaches and is optimistic on that
    axis. It is a P&L and daily-wall measurement, not a total-wall clearance.
    The unchunked E5 tenyear arm is the authority on the total wall — and it
    already showed the 2015-01-15 CHF unpeg breaching it on day 13.

Run:  uv run python3 backtest/src/e6_decade_chunked.py [--start-year 2015]
"""
import argparse, importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_e = importlib.util.spec_from_file_location("e5", str(HERE / "e5_validate_winner.py"))
e5 = importlib.util.module_from_spec(_e); _e.loader.exec_module(e5)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

SCALE_CAP = os.environ.get("E6_SCALE_CAP", "175000")


def run_year(env, tp, start, end, balance, scale_cap):
    e = dict(os.environ); e.update(cs.dh.BASE_ENV); e.update(env)
    e["FIVEERS_MAX_SCALE"] = str(scale_cap)
    e["OPT_PARAMS"] = json.dumps({**cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        subprocess.run([sys.executable, str(cs.dh.BACKTEST), "--start", start,
                        "--end", end, "--balance", f"{balance:.2f}",
                        "--output", td, "--quiet"],
                       env=e, cwd=str(cs.dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=7200)
        rj = Path(td) / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        return {"net_pnl": r.get("net_pnl"), "final_balance": r.get("final_balance"),
                "withdrawn": r.get("fiveers_total_withdrawn"),
                "final_funded_level": r.get("fiveers_final_funded_level"),
                "scaling_events": r.get("fiveers_scaling_events"),
                "max_tdd_pct": r.get("max_tdd_pct"), "max_ddd_pct": r.get("max_ddd_pct"),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "account_failed": r.get("account_failed"), "fail_info": r.get("fail_info")}
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--end-year", type=int, default=2024)
    ap.add_argument("--first-start", default=None,
                    help="override the first year's start date, e.g. 2015-02-01 to skip the CHF unpeg")
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    out = DOE_DIR / "e6_decade.json"
    res = json.loads(out.read_text()) if out.exists() else {}

    env = dict(e5.WINNER_ENV)
    tp = dict(e5.TP); tp["risk_per_trade_pct"] = e5.WINNER_RISK

    balance = res.get("_carry_balance", 100_000.0)
    print(f"[E6] decade in yearly chunks, funded 100k, scaling cap ${SCALE_CAP}", flush=True)
    print(f"{'year':>6} {'net':>12} {'balance':>12} {'withdrawn':>11} "
          f"{'maxDDD':>7} {'maxTDD':>7} {'trades':>7} {'failed':>7}", flush=True)

    total_withdrawn = res.get("_carry_withdrawn", 0.0)
    for y in range(args.start_year, args.end_year + 1):
        key = str(y)
        if key not in res:
            start = args.first_start if (y == args.start_year and args.first_start) else f"{y}-01-01"
            m = run_year(env, tp, start, f"{y}-12-31", balance, SCALE_CAP)
            m["_start_balance"] = balance
            res[key] = m
            if not m.get("error") and m.get("final_balance"):
                balance = m["final_balance"]
                total_withdrawn += (m.get("withdrawn") or 0.0)
            res["_carry_balance"] = balance
            res["_carry_withdrawn"] = total_withdrawn
            out.write_text(json.dumps(res, indent=2))
        else:
            m = res[key]
            if m.get("final_balance"):
                balance = m["final_balance"]

        if m.get("error"):
            print(f"{y:>6}  ERROR {m['error']}", flush=True); continue
        print(f"{y:>6} {m['net_pnl']:>12,.0f} {m['final_balance']:>12,.0f} "
              f"{(m.get('withdrawn') or 0):>11,.0f} {m['max_ddd_pct']:>6.2f}% "
              f"{m['max_tdd_pct']:>6.2f}% {m['trades']:>7} {str(m['account_failed']):>7}",
              flush=True)
        if m["account_failed"]:
            print(f"        ^ {m.get('fail_info', {}).get('reason', '')}", flush=True)

    yrs = [res[str(y)] for y in range(args.start_year, args.end_year + 1)
           if str(y) in res and not res[str(y)].get("error")]
    if yrs:
        print(f"\n[E6] {len(yrs)} years | total withdrawn ${total_withdrawn:,.0f} "
              f"| final balance ${balance:,.0f}", flush=True)
        print(f"  worst daily DD any year : {max(x['max_ddd_pct'] for x in yrs):.2f}%  (3% wall)",
              flush=True)
        print(f"  years the account died  : {sum(1 for x in yrs if x['account_failed'])}",
              flush=True)
    print("[e6_decade_chunked] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
