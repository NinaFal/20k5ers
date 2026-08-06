#!/usr/bin/env python3
"""
Diagnose the single holdout breach: start 2019-07-31.

That start passed Step 1 in 13 days and then breached during Step 2, so Step 2
begins on 2019-08-14 (start + d1 + 1) with a fresh $100k. This re-runs that
window keeping the full results rather than the pass/fail summary the holdout
stores.

Why this start matters out of proportion to its count: the decade gauntlet and
the continuous account both begin every account on 2 January, so neither can
reach a mid-August window. Both report 2019 as clean at 2.24% worst daily. This
start proves that verdict is a property of the sampling, not of the year.

First pass established: died 2019-08-20 13:45 UTC, day 6 of Step 2, daily wall
at 5.13% — 0.13 points over. Total drawdown peaked at 1.6%, so the 10% wall was
never in play. safety_events 5, ddd_halts 2, ddd_halts_midbar 0, and the failure
is tagged [bar].

That 0.13-point margin is the reason for the second arm here. Breach detection
runs against TDD_WORST_CASE marking, which marks every open position to its M15
bar's adverse extreme and assumes they all get there together — a deliberate
upper bound, not a prediction. Re-running the identical window on bar-close
marking brackets the truth: worst-case is the ceiling, bar-close the floor, and
a real tick-level path sits between them. If bar-close survives, this account
died to the measurement convention rather than unambiguously to the market, and
the honest description is "on the edge" rather than "breached".

The close model is NOT a confound: DDD_CLOSE_AT_TRIGGER is already 1 in the
winner's environment, so a fired halt closes at the trigger mark exactly as
live's 5-second thread does, not at the bar's worst wick.

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
MARKS = (("worstcase", "1"), ("barclose", "0"))


def run(worst_case: str, tag: str) -> dict:
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    env = dict(os.environ); env.update(w5.cs.dh.BASE_ENV)
    env.update(w5.BASE_ENV); env.update(b["env"])
    env["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    env["TDD_WORST_CASE"] = worst_case
    env.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    env["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    env["PYTHONUTF8"] = "1"

    end = (date.fromisoformat(STEP2_START) + timedelta(days=w5.HORIZON)).isoformat()
    d = w5.DOE_DIR / "tmp" / f"diag_20190731_{tag}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", STEP2_START, "--end", end,
                        "--balance", "100000", "--output", str(d), "--quiet"],
                       env=env, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=3600)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        fi = r.get("fail_info") or {}
        out = {
            "marking": tag, "TDD_WORST_CASE": worst_case,
            "account_failed": bool(r.get("account_failed")),
            "fail_reason": fi.get("reason"), "fail_time": fi.get("time"),
            "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
            # Counts, not lists — an earlier version of this script read the list
            # form, found it empty, and wrongly reported that nothing fired.
            "safety_events": r.get("safety_events"),
            "ddd_halts": r.get("ddd_halts"),
            "ddd_halts_midbar": r.get("ddd_halts_midbar"),
        }
        if fi.get("time"):
            try:
                out["breach_day_of_step2"] = (date.fromisoformat(str(fi["time"])[:10])
                                              - date.fromisoformat(STEP2_START)).days
            except ValueError:
                pass
        return out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    res = w5.load_json(OUT)
    if "marking" in res:            # first-pass format — start clean
        res = {}
    print(f"[diag] Step 2 window {STEP2_START} -> "
          f"{(date.fromisoformat(STEP2_START) + timedelta(days=w5.HORIZON)).isoformat()}"
          f"  wall 5.0%  balance $100,000", flush=True)
    for tag, wc in MARKS:
        if tag in res:
            continue
        print(f"\n[diag] marking={tag} (TDD_WORST_CASE={wc})", flush=True)
        res[tag] = run(wc, tag)
        w5.atomic_write(OUT, res)
        r = res[tag]
        if r.get("error"):
            print(f"[diag] {tag}: ERROR {r['error']}", flush=True); continue
        print(f"[diag]   failed {r['account_failed']}  reason {r['fail_reason']}", flush=True)
        print(f"[diag]   when {r['fail_time']}  day {r.get('breach_day_of_step2')}", flush=True)
        print(f"[diag]   worst DDD {r['max_ddd_pct']}%  worst TDD {r['max_tdd_pct']}%  "
              f"trades {r['trades']}  win {r['win_rate']}%", flush=True)
        print(f"[diag]   safety_events {r['safety_events']}  ddd_halts {r['ddd_halts']}  "
              f"midbar {r['ddd_halts_midbar']}", flush=True)

    a, b = res.get("worstcase") or {}, res.get("barclose") or {}
    if a and b and not a.get("error") and not b.get("error"):
        print("\n" + "=" * 66, flush=True)
        print("[diag] SAME WINDOW, SAME CONFIG — ONLY THE MARKING CONVENTION DIFFERS", flush=True)
        print(f"  worst-case (ceiling)  DDD {a['max_ddd_pct']}%  "
              f"{'BREACHED' if a['account_failed'] else 'survived'}", flush=True)
        print(f"  bar-close  (floor)    DDD {b['max_ddd_pct']}%  "
              f"{'BREACHED' if b['account_failed'] else 'survived'}", flush=True)
        if a["account_failed"] and not b["account_failed"]:
            print("\n  The truth is between these. This start is ON THE EDGE — it dies\n"
                  "  under the pessimistic convention and survives under the optimistic\n"
                  "  one, so it should not be reported as an unambiguous breach.", flush=True)
        elif a["account_failed"] and b["account_failed"]:
            print("\n  Breaches under BOTH conventions — a real breach, not an artefact\n"
                  "  of worst-case marking.", flush=True)
    print("[w5_diag_breach_20190731] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
