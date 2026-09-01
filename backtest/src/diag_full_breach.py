#!/usr/bin/env python3
"""
Diagnose WHY every Stage-5c trial breaches the full 2015-2024 window.

Runs a chosen trial's exact config on the full window with a PERSISTENT output
dir (keeps trades.csv + tdd_series.csv + fail_info), then reports:
  - the breach date / type / funded level
  - the positions open (and their symbols) around the breach day
so we can see which instrument's gap drives the daily blow-up.

Usage:  python3 diag_full_breach.py <trial_id> [--exclude SYM1,SYM2]
"""
import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOE_DIR = REPO / "backtest" / "output" / "doe"

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dh)

# Pull the exact screen config (entry + ladder) so the run matches the screen.
_s = importlib.util.spec_from_file_location("scr", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s)
# stage5c_oos_screen imports doe_harness at module scope only inside main()? No —
# it's safe to exec; it only defines constants + main().
_s.loader.exec_module(scr)


def load_trial_env(trial_id: int) -> dict:
    j = json.loads((DOE_DIR / "stage5c_oos_screen.json").read_text())
    for r in j:
        if int(r["trial"]) == trial_id:
            return r["env"]
    raise SystemExit(f"trial {trial_id} not found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trial", type=int)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--corr-cap", type=int, default=0)
    ap.add_argument("--max-scale", default="", help="override FIVEERS_MAX_SCALE")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2024-12-31")
    args = ap.parse_args()

    env_over = load_trial_env(args.trial)
    tag = f"t{args.trial}" + (f"_excl" if args.exclude else "") \
        + (f"_cc{args.corr_cap}" if args.corr_cap else "") \
        + (f"_ms{args.max_scale}" if args.max_scale else "")
    outdir = DOE_DIR / f"diag_{tag}_{args.start}"
    outdir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update(dh.BASE_ENV)
    env.update(env_over)
    if args.exclude:
        env["EXCLUDE_SYMBOLS"] = args.exclude
    if args.corr_cap:
        env["CORR_GROUP_CAP"] = str(args.corr_cap)
    if args.max_scale:
        env["FIVEERS_MAX_SCALE"] = str(args.max_scale)
    env["OPT_PARAMS"] = json.dumps({**dh.BASE_TP, **scr.TP_OVER})
    env["PYTHONUTF8"] = "1"

    cmd = [sys.executable, str(dh.BACKTEST),
           "--start", args.start, "--end", args.end,
           "--balance", "50000", "--output", str(outdir), "--quiet"]
    print(f"[diag] running {tag}  {args.start}->{args.end}"
          f"  exclude={args.exclude or '(none)'}", flush=True)
    p = subprocess.run(cmd, env=env, cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=3000)
    rj = outdir / "results.json"
    if p.returncode != 0 or not rj.exists():
        print("[diag] RUN FAILED rc=", p.returncode, flush=True)
        print(p.stderr[-3000:])
        return
    r = json.loads(rj.read_text())
    fi = r.get("fail_info") or {}
    print("\n===== RESULT", tag, "=====", flush=True)
    print(f"  account_failed : {r.get('account_failed')}")
    print(f"  net_pnl        : {r.get('net_pnl'):,.0f}")
    print(f"  max_tdd_pct    : {r.get('max_tdd_pct')}")
    print(f"  max_ddd_pct    : {r.get('max_ddd_pct')}")
    print(f"  final_funded   : {r.get('fiveers_final_funded_level')}")
    print(f"  scalings       : {r.get('fiveers_scaling_events')}")
    print(f"  breach_type    : {fi.get('breach_type')}")
    print(f"  breach_time    : {fi.get('time')}")
    print(f"  funded@fail    : {fi.get('funded_level_at_failure')}")

    # Find the breach day and dump the trades that were open into it.
    bt = fi.get("time")
    tf = outdir / "trades.csv"
    if bt and tf.exists():
        try:
            bday = str(bt)[:10]
            prev = (datetime.fromisoformat(str(bt)[:19]) - timedelta(days=4)).date().isoformat()
        except Exception:
            bday, prev = str(bt)[:10], ""
        rows = list(csv.DictReader(open(tf)))
        # Which symbols were live in the window [breach-4d, breach]?
        near = []
        for row in rows:
            ot = (row.get("entry_time") or row.get("open_time") or "")[:10]
            ct = (row.get("exit_time") or row.get("close_time") or "")[:10]
            if (ot and ot <= bday) and (not ct or ct >= (prev or bday)):
                near.append(row)
        sym_key = "symbol" if rows and "symbol" in rows[0] else (
            "Symbol" if rows and "Symbol" in rows[0] else None)
        print(f"\n  breach day {bday}; trades live near breach: {len(near)}")
        if sym_key:
            c = Counter(row.get(sym_key, "?") for row in near)
            for s, n in c.most_common():
                print(f"    {s:<12} x{n}")
        # show the raw columns available for deeper drill
        if rows:
            print("  trades.csv cols:", list(rows[0].keys()))
    print("\n[diag] outdir:", outdir, flush=True)


if __name__ == "__main__":
    main()
