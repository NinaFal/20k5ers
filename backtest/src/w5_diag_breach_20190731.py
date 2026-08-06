#!/usr/bin/env python3
"""
Diagnose the single holdout breach: start 2019-07-31.

That start passed Step 1 in 13 days and then breached during Step 2. Step 2
therefore begins on 2019-08-14 (start + d1 + 1) with a fresh $100k, which is
what this re-runs — same config, same wall, but keeping the full results rather
than the pass/fail summary the holdout stores.

Why this start matters out of proportion to its count: the decade gauntlet and
the continuous account both begin every account on 2 January, so neither can
reach a mid-August window. Both report 2019 as clean at 2.24% worst daily. This
start proves that verdict is a property of the sampling, not of the year.

The questions this answers:
  * which wall killed it, daily or total
  * on what date, and how far into Step 2
  * what the safety tiers were doing at the time — whether the halt, the
    cautious/conservative risk tiers and the nightly de-risk fired and were
    simply outrun, or never engaged at all

Run:  uv run python3 backtest/src/w5_diag_breach_20190731.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

HOLDOUT_START = "2019-07-31"
D1 = 13                                   # Step 1 pass day, from holdout100.json
STEP2_START = (date.fromisoformat(HOLDOUT_START) + timedelta(days=D1 + 1)).isoformat()
OUT = w5.W5_DIR / "diag_breach_20190731.json"


def main():
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    env = dict(os.environ); env.update(w5.cs.dh.BASE_ENV)
    env.update(w5.BASE_ENV); env.update(b["env"])
    env["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    env.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    env["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    env["PYTHONUTF8"] = "1"

    end = (date.fromisoformat(STEP2_START) + timedelta(days=w5.HORIZON)).isoformat()
    d = w5.DOE_DIR / "tmp" / "diag_20190731"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    print(f"[diag] Step 2 window {STEP2_START} -> {end}  wall "
          f"{env['CFG_DAILY_WALL_PCT']}%  balance $100,000", flush=True)
    subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                    "--start", STEP2_START, "--end", end,
                    "--balance", "100000", "--output", str(d), "--quiet"],
                   env=env, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=3600)
    rj = d / "results.json"
    if not rj.exists():
        print("[diag] no results.json", flush=True); return
    r = json.loads(rj.read_text())
    fi = r.get("fail_info") or {}
    # results.json reports safety_events as a COUNT in some builds and as the
    # event list in others; tolerate both rather than assuming.
    ev = r.get("safety_events")
    ev_count = ev if isinstance(ev, int) else None
    if not isinstance(ev, list):
        ev = r.get("safety_events_detail") or r.get("safety_event_log") or []
    if not isinstance(ev, list):
        ev = []

    summary = {
        "holdout_start": HOLDOUT_START, "step2_start": STEP2_START,
        "wall_pct": env["CFG_DAILY_WALL_PCT"],
        "account_failed": r.get("account_failed"),
        "fail_reason": fi.get("reason"), "fail_time": fi.get("time"),
        "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
        "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
        "safety_event_counts": {},
        "safety_events_total": ev_count,
        "results_keys": sorted(r.keys()),
    }
    for e in ev:
        t = e.get("type", "?")
        summary["safety_event_counts"][t] = summary["safety_event_counts"].get(t, 0) + 1

    print(f"\n[diag] failed      {summary['account_failed']}", flush=True)
    print(f"[diag] reason      {summary['fail_reason']}", flush=True)
    print(f"[diag] when        {summary['fail_time']}", flush=True)
    if fi.get("time"):
        try:
            dd = (date.fromisoformat(str(fi["time"])[:10])
                  - date.fromisoformat(STEP2_START)).days
            print(f"[diag] day of Step 2  {dd}", flush=True)
            summary["breach_day_of_step2"] = dd
        except ValueError:
            pass
    print(f"[diag] worst DDD   {summary['max_ddd_pct']}%   worst TDD "
          f"{summary['max_tdd_pct']}%", flush=True)
    print(f"[diag] trades      {summary['trades']}  win {summary['win_rate']}%", flush=True)
    print(f"[diag] safety events fired: {summary['safety_event_counts'] or 'NONE'}", flush=True)

    # The events immediately around the kill are what say whether the protection
    # engaged and was outrun, or never engaged at all.
    if fi.get("time"):
        cutoff = str(fi["time"])[:10]
        near = [e for e in ev if str(e.get("time", ""))[:10] == cutoff]
        summary["events_on_breach_day"] = near
        print(f"\n[diag] events on {cutoff}: {len(near)}", flush=True)
        for e in near[:25]:
            print("   " + json.dumps(e), flush=True)

    w5.atomic_write(OUT, summary)
    shutil.rmtree(d, ignore_errors=True)
    print("[w5_diag_breach_20190731] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
