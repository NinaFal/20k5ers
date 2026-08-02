#!/usr/bin/env python3
"""
E9 — how fast does the 2-step challenge pass, over 100 random start dates?

The quarterly grid (Jan/Apr/Jul/Oct) is only 16 samples and every one begins on
a quarter boundary. 100 random dates drawn across 2016-2025 give a far better
picture of the actual distribution of time-to-pass, and of how often an attempt
dies instead.

Reports the full distribution — not just a median — because what matters for a
challenge is the spread: the p10 tells you the good case, the p90 tells you how
long a bad-but-surviving attempt drags on, and the breach rate tells you how
often you lose the fee.

Per-start cached: this container restarts constantly, so a kill costs at most
one start.

Run:  uv run python3 backtest/src/e9_random100.py [--n 100] [--horizon 75]
"""
import argparse, concurrent.futures, importlib.util, json, os, random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_e = importlib.util.spec_from_file_location("e5", str(HERE / "e5_validate_winner.py"))
e5 = importlib.util.module_from_spec(_e); _e.loader.exec_module(e5)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")
WORKERS = int(os.environ.get("E9_WORKERS", str(os.cpu_count() or 2)))


def draw_starts(n, seed):
    """Random weekday starts, 2016-01-01 .. 2025-06-30 (room for a 2-step run)."""
    rng = random.Random(seed)
    lo, hi = date(2016, 1, 1), date(2025, 6, 30)
    span = (hi - lo).days
    out = set()
    while len(out) < n:
        d = lo + timedelta(days=rng.randrange(span))
        if d.weekday() < 5:                      # start on a weekday
            out.add(d.isoformat())
    return sorted(out)


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--horizon", type=int, default=75)
    ap.add_argument("--seed", type=int, default=20260728)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    out = DOE_DIR / "e9_random100.json"
    res = json.loads(out.read_text()) if out.exists() else {}
    store = res.setdefault("starts", {})

    env = dict(e5.WINNER_ENV)
    tp = dict(e5.TP); tp["risk_per_trade_pct"] = e5.WINNER_RISK
    starts = draw_starts(args.n, args.seed)
    res["_starts_list"] = starts
    todo = [s for s in starts if s not in store]
    print(f"[E9] {len(starts)} random starts 2016-2025 | {len(store)} cached, "
          f"{len(todo)} to run | horizon {args.horizon}d/step | {WORKERS} workers", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(cs.full_two_step, env, tp, s, args.horizon): s for s in todo}
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            s = futs[fut]
            r = fut.result(); r.pop("detail", None)
            store[s] = r
            out.write_text(json.dumps(res, indent=2))
            tag = "BREACH" if r["breach"] else (f"pass {r['total']}d" if r.get("total") else "no pass")
            print(f"  [{len(store):3d}/{len(starts)}] {s}  {tag}", flush=True)

    rows = [store[s] for s in starts if s in store]
    n = len(rows)
    if not n:
        print("[E9] nothing to report", flush=True); return
    breach = [r for r in rows if r["breach"]]
    passed = sorted(r["total"] for r in rows if r.get("total") is not None)
    nopass = n - len(passed) - len(breach)

    print(f"\n[E9] RESULTS over {n} random starts", flush=True)
    print(f"  passed both steps : {len(passed):3d}  ({100*len(passed)/n:.1f}%)", flush=True)
    print(f"  breached (dead)   : {len(breach):3d}  ({100*len(breach)/n:.1f}%)", flush=True)
    print(f"  alive but unfinished within {args.horizon}d/step : {nopass:3d}  ({100*nopass/n:.1f}%)",
          flush=True)
    if passed:
        print(f"\n  days to pass BOTH steps (of the {len(passed)} that passed):", flush=True)
        for q, lbl in ((0.10, "p10 (fast)"), (0.25, "p25"), (0.50, "median"),
                       (0.75, "p75"), (0.90, "p90 (slow)")):
            print(f"    {lbl:12}: {pct(passed, q)} days", flush=True)
        print(f"    fastest     : {passed[0]} days", flush=True)
        print(f"    slowest     : {passed[-1]} days", flush=True)
        print(f"\n  cumulative pass rate over ALL {n} attempts:", flush=True)
        for d in (20, 30, 40, 50, 60, 75, 90, 120):
            k = sum(1 for t in passed if t <= d)
            print(f"    within {d:3d} days: {k:3d}  ({100*k/n:.1f}%)", flush=True)
    print("[e9_random100] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
