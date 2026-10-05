#!/usr/bin/env python3
"""
What actually happens to the stalled starts, given 5ers imposes NO time limit?

Both holdouts scored a start as "stalled" when it failed to reach the target
inside a 75-day-per-step horizon. That horizon is a measurement choice, not a
5ers rule: the5ers publish "Max Trading Period: Unlimited" for both steps, and
the only time constraint is that an account idle for 30 consecutive days
expires - irrelevant for a strategy trading ~1,000 times a year.

So a stall is not a lost challenge. It is an UNRESOLVED one. The account is
still alive and still trading toward the target, and it will eventually do one
of two things: pass, or breach. Censoring at 75 days hides which.

This re-runs every stalled start from both holdouts at a 250-day horizon -
long enough to resolve almost all of them - and reports the split.

Why it matters for planning: if stalls mostly resolve to passes, the true
per-attempt failure rate is close to the 4.6% breach rate alone, and the
effective pass rate approaches 95%. If they mostly resolve to breaches, the
failure rate is closer to 11% and the fee economics are materially worse. The
two readings differ by a factor of two and nothing measured so far distinguishes
them.

Run:  uv run python3 backtest/src/w5_stalls_resolved.py
"""
import concurrent.futures, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

LONG_HORIZON = 250          # vs the 75 used for scoring
OUT = w5.W5_DIR / "stalls_resolved.json"


def stalled_starts():
    """Every start scored as a stall in either holdout: survived, never passed."""
    out = []
    for f in ("holdout100.json", "holdout2.json"):
        p = w5.W5_DIR / f
        if not p.exists():
            continue
        for s, v in json.loads(p.read_text()).items():
            if v.get("total") is None and not v.get("breach"):
                out.append((s, f))
    return sorted(set(out))


def main():
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    starts = stalled_starts()
    res = w5.load_json(OUT)
    todo = [s for s, _ in starts if s not in res]
    print(f"[stalls] {len(starts)} stalled starts from both holdouts, "
          f"{len(todo)} to run at {LONG_HORIZON}d/step (was 75)", flush=True)
    for s, src in starts:
        print(f"   {s}  ({src})", flush=True)

    chunk = max(2, w5.WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, LONG_HORIZON): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                res[futs[f]] = r
            w5.atomic_write(OUT, res)
            print(f"[stalls] {len(res)}/{len(starts)} resolved", flush=True)

    rows = {s: res[s] for s, _ in starts if s in res}
    passed = {s: v["total"] for s, v in rows.items() if v.get("total") is not None}
    breached = [s for s, v in rows.items() if v.get("breach")]
    still = [s for s, v in rows.items()
             if v.get("total") is None and not v.get("breach")]
    n = len(rows)
    print("\n" + "=" * 66, flush=True)
    print(f"[stalls] {n} PREVIOUSLY-STALLED STARTS AT {LONG_HORIZON}d", flush=True)
    print(f"  eventually PASSED   {len(passed):>3}/{n}", flush=True)
    print(f"  eventually BREACHED {len(breached):>3}/{n}", flush=True)
    print(f"  still unresolved    {len(still):>3}/{n}", flush=True)
    if passed:
        d = sorted(passed.values())
        print(f"  days to pass: median {d[len(d)//2]}  min {d[0]}  max {d[-1]}", flush=True)
        for s, t in sorted(passed.items()):
            print(f"     {s} -> {t}d", flush=True)
    if breached:
        print(f"  breached: {breached}", flush=True)
    if still:
        print(f"  unresolved: {still}", flush=True)
    print("[w5_stalls_resolved] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
