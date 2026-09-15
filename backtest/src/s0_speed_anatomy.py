#!/usr/bin/env python3
"""
S0 — speed anatomy: WHY does a pass take ~94 days?

Every stage so far tuned parameters against a scalar (days-to-pass) without
ever asking what those days are made of. E0 did exactly this for breaches —
measure first, then search — and overturned a conclusion reached from ~2,700
blind backtests. This is the same move for slowness.

Four candidate causes, each implying a different stage:

  1. THE 3-PROFITABLE-DAYS RULE, not the profit target. A step passes on
     max(day the +8% is reached, day of the 3rd >=$500 day). If the target is
     hit early and the rule is what drags, no amount of extra edge helps and
     the fix is trade SCHEDULING, not sizing or entries.
  2. TOO FEW SETUPS — long idle stretches. Fix: loosen entry gates.
  3. LOW WIN RATE / small average win — grinding. Fix: selectivity, ladder.
  4. SELF-INFLICTED BRAKING — days lost to DDD halts and reduced-risk tiers.
     Fix: the halt and TDD ladder.

Runs STEP 1 only (the accumulation phase that dominates the timeline), keeps
each run's trade log, and reports the decomposition. Per-start cached.

Run:  uv run python3 backtest/src/s0_speed_anatomy.py [--n 30]
"""
import argparse, concurrent.futures, importlib.util, json, os, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_e = importlib.util.spec_from_file_location("e5", str(HERE / "e5_validate_winner.py"))
e5 = importlib.util.module_from_spec(_e); _e.loader.exec_module(e5)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")
WORKERS = int(os.environ.get("S0_WORKERS", str(os.cpu_count() or 2)))
CANON = DOE_DIR / "CANONICAL_100_STARTS.json"


def run_step1(env_over, tp_over, start, horizon):
    """One step-1 run, keeping the trade log for anatomy."""
    s = date.fromisoformat(start)
    end = (s + timedelta(days=horizon)).isoformat()
    env = dict(os.environ); env.update(cs.dh.BASE_ENV); env.update(env_over)
    env["CFG_DAILY_WALL_PCT"] = env_over.get("CFG_DAILY_WALL_PCT", cs.DAILY_WALL_PCT)
    env["OPT_PARAMS"] = json.dumps({**cs.dh.BASE_TP, **tp_over})
    env["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        subprocess.run([sys.executable, str(cs.dh.BACKTEST), "--start", start,
                        "--end", end, "--balance", str(cs.ACCOUNT),
                        "--output", td, "--quiet"],
                       env=env, cwd=str(cs.dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=3600)
        rj, tf = Path(td) / "results.json", Path(td) / "trades.csv"
        if not rj.exists():
            return {"error": "no results"}
        r = json.loads(rj.read_text())

        # replay the pass logic so we can see WHICH condition bound
        by_day = {}
        n_trades = n_win = 0
        gross_win = gross_loss = 0.0
        if tf.exists():
            t = pd.read_csv(tf)
            for _, row in t.iterrows():
                d = str(row.get("close_time") or "")[:10]
                if not d:
                    continue
                v = float(row.get("pnl") or 0) + float(row.get("swap") or 0)
                by_day[d] = by_day.get(d, 0.0) + v
                # pandas gives NaN for a blank 'partial' cell, and bool(nan) is
                # True — which silently classified every full close as a partial
                # and zeroed the trade stats. Compare explicitly.
                _p = row.get("partial", False)
                is_partial = str(_p).strip().lower() in ("true", "1", "1.0")
                if not is_partial:
                    n_trades += 1
                    if v > 0:
                        n_win += 1; gross_win += v
                    else:
                        gross_loss += v

        cum = 0.0; target_day = None; profit_days = 0; third = None
        for d in sorted(by_day):
            cum += by_day[d]
            elapsed = (date.fromisoformat(d) - s).days
            if by_day[d] >= cs.PROFITABLE_DAY_USD:
                profit_days += 1
                if profit_days == cs.MIN_PROFITABLE_DAYS and third is None:
                    third = elapsed
            if target_day is None and cum >= cs.STEP1_TARGET:
                target_day = elapsed
        pass_day = max(target_day, third) if (target_day is not None and third is not None) else None

        active = len(by_day)
        span = max((date.fromisoformat(max(by_day)) - s).days, 1) if by_day else 1
        return {
            "pass_day": pass_day, "target_day": target_day, "third_profit_day": third,
            "profitable_days": profit_days,
            "bound_by": (None if pass_day is None else
                         ("3-day rule" if (third or 0) > (target_day or 0) else "profit target")),
            "active_days": active, "span_days": span,
            "idle_ratio": round(1 - active / span, 3),
            "trades": n_trades, "win_rate": round(n_win / n_trades, 3) if n_trades else None,
            "avg_win": round(gross_win / n_win, 2) if n_win else None,
            "avg_loss": round(gross_loss / (n_trades - n_win), 2) if (n_trades - n_win) else None,
            "net": round(sum(by_day.values()), 2),
            "usd_per_active_day": round(sum(by_day.values()) / active, 2) if active else None,
            "ddd_halts": r.get("ddd_halts"), "ddd_reduces": r.get("ddd_reduces"),
            "account_failed": r.get("account_failed"),
        }
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--horizon", type=int, default=75)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    out = DOE_DIR / "s0_speed_anatomy.json"
    res = json.loads(out.read_text()) if out.exists() else {}

    starts = json.loads(CANON.read_text())["starts"][:args.n]
    env = dict(e5.WINNER_ENV)
    tp = dict(e5.TP); tp["risk_per_trade_pct"] = e5.WINNER_RISK
    todo = [s for s in starts if s not in res]
    print(f"[S0] step-1 anatomy over {len(starts)} canonical starts "
          f"({len(res)} cached, {len(todo)} to run), {WORKERS} workers", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(run_step1, env, tp, s, args.horizon): s for s in todo}
        for fut in concurrent.futures.as_completed(futs):
            s = futs[fut]
            res[s] = fut.result()
            out.write_text(json.dumps(res, indent=2))
            m = res[s]
            print(f"  [{len(res):3d}/{len(starts)}] {s}  pass={m.get('pass_day')} "
                  f"target={m.get('target_day')} third={m.get('third_profit_day')} "
                  f"bound={m.get('bound_by')}", flush=True)

    rows = [res[s] for s in starts if s in res and not res[s].get("error")]
    ok = [r for r in rows if r.get("pass_day") is not None]
    if not ok:
        print("\n[S0] no step-1 passes to analyse", flush=True); return

    def med(vals):
        v = sorted(x for x in vals if x is not None)
        return v[len(v) // 2] if v else None

    bound = {}
    for r in ok:
        bound[r["bound_by"]] = bound.get(r["bound_by"], 0) + 1

    print(f"\n[S0] STEP-1 ANATOMY over {len(rows)} starts ({len(ok)} passed)", flush=True)
    print(f"\n  WHAT GATES THE PASS:", flush=True)
    for k, v in sorted(bound.items(), key=lambda kv: -kv[1]):
        print(f"    {k:15}: {v:3d}  ({100*v/len(ok):.0f}%)", flush=True)
    print(f"\n  median day the +8% target is reached : {med(r['target_day'] for r in ok)}", flush=True)
    print(f"  median day the 3rd profitable day lands: {med(r['third_profit_day'] for r in ok)}", flush=True)
    print(f"  median step-1 pass day                 : {med(r['pass_day'] for r in ok)}", flush=True)
    print(f"\n  ACTIVITY:", flush=True)
    print(f"    median trades (step 1)      : {med(r['trades'] for r in rows)}", flush=True)
    print(f"    median active (trading) days: {med(r['active_days'] for r in rows)}", flush=True)
    print(f"    median idle ratio           : {med(r['idle_ratio'] for r in rows)}", flush=True)
    print(f"    median $/active day         : {med(r['usd_per_active_day'] for r in rows)}", flush=True)
    print(f"\n  EDGE:", flush=True)
    print(f"    median win rate : {med(r['win_rate'] for r in rows)}", flush=True)
    print(f"    median avg win  : {med(r['avg_win'] for r in rows)}", flush=True)
    print(f"    median avg loss : {med(r['avg_loss'] for r in rows)}", flush=True)
    print(f"\n  SELF-BRAKING:", flush=True)
    print(f"    median DDD halts   : {med(r['ddd_halts'] for r in rows)}", flush=True)
    print(f"    median DDD reduces : {med(r['ddd_reduces'] for r in rows)}", flush=True)
    print(f"    breached           : {sum(1 for r in rows if r.get('account_failed'))}/{len(rows)}", flush=True)
    print("\n[s0_speed_anatomy] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
