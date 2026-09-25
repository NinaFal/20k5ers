#!/usr/bin/env python3
"""
TRUE HOLDOUT: 100 fresh random starts, 2015-2025, on the round's winner.

Every number in this round came from the same 25 canonical starts drawn from
2016-01-18 onward. The winning config was selected against those windows, so
they can no longer measure it honestly — a config picked on a sample is
flattered by that sample. This draws 100 NEW starts with a different seed and
extends the range back to 2015, which no arm of this project has ever touched.

2015 matters specifically: the January 2015 CHF unpeg is in it, and earlier
work in this project found that event kills accounts through the TOTAL wall
regardless of daily control. If the winner survives 2015 starts, that is worth
knowing; if it does not, that is worth knowing more.

Differences from the screening evaluator, both deliberate:

  * NO EARLY ABORT. w5_common.evaluate stops a config at its first breach
    because a breaching config is rejected anyway. Here the question is "how
    often does it breach", so every start runs to completion.
  * Per-start results are kept individually so a breach can be traced to its
    window rather than just counted.

Run:  uv run python3 backtest/src/w5_holdout100.py
"""
import concurrent.futures, importlib.util, json, random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

SEED = 20260805                     # deliberately NOT the canonical seed (20260728)
N = 100
FIRST = date(2015, 1, 5)            # 2015 has never been in any arm of this round
LAST = date(2025, 6, 17)            # same data bound as the canonical list
STARTS_FILE = w5.DOE_DIR / "HOLDOUT_100_STARTS_2015.json"


def build_starts():
    """100 distinct weekday starts, frozen to a tracked file on first run."""
    if STARTS_FILE.exists():
        return json.loads(STARTS_FILE.read_text())["starts"]
    rng = random.Random(SEED)
    span = (LAST - FIRST).days
    seen = set()
    while len(seen) < N:
        d = FIRST + timedelta(days=rng.randint(0, span))
        if d.weekday() < 5:
            seen.add(d.isoformat())
    starts = sorted(seen)
    w5.atomic_write(STARTS_FILE, {"seed": SEED, "first": FIRST.isoformat(),
                                  "last": LAST.isoformat(), "n": N, "starts": starts})
    return starts


def winner_config():
    """t65 (nightly) + the TDD-tier tightening that carried it through the decade."""
    c = [x for x in json.loads((w5.W5_DIR / "nightly_top20.json").read_text())
         if str(x["trial"]) == "65"][0]
    env = dict(w5.BASE_ENV); env.update(c["env"])
    env["TDD_WORST_CASE"] = "1"
    env.update({"CFG_DAILY_HALT_PCT": "2.50", "TDD_WALL_SAFETY": "5.5",
                "CFG_TDD_CAUTION_PCT": "1.5", "CFG_RISK_CAUTIOUS": "0.4",
                "CFG_TDD_WARNING_PCT": "2.5", "CFG_RISK_CONSERVATIVE": "0.25"})
    tp = dict(w5.BASE_TP); tp.update(c["tp"])
    return env, tp


def main():
    starts = build_starts()
    env, tp = winner_config()
    out = w5.W5_DIR / "holdout100.json"
    res = w5.load_json(out)
    todo = [s for s in starts if s not in res]
    print(f"[holdout] {len(starts)} starts {starts[0]}..{starts[-1]} "
          f"| {len(res)} cached, {len(todo)} to run | NO early abort", flush=True)

    chunk = max(2, w5.WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                res[futs[f]] = r
            w5.atomic_write(out, res)
            done = len(res)
            br = sum(1 for v in res.values() if v.get("breach"))
            tot = sorted(v["total"] for v in res.values() if v.get("total") is not None)
            print(f"[holdout] {done}/{len(starts)}  breaches {br}  "
                  f"completed {len(tot)}  median {tot[len(tot)//2] if tot else '-'}", flush=True)

    rows = [res[s] for s in starts if s in res]
    n = len(rows)
    br = [s for s in starts if res.get(s, {}).get("breach")]
    tot = sorted(v["total"] for v in rows if v.get("total") is not None)
    print("\n" + "=" * 62, flush=True)
    print(f"[holdout] 100 FRESH STARTS 2015-2025 — winner (t65 + TDD tiers)", flush=True)
    print(f"  breaches      {len(br)}/{n}  ({len(br)/n*100:.0f}%)", flush=True)
    print(f"  completed     {len(tot)}/{n}", flush=True)
    if tot:
        print(f"  pass <=30d    {sum(1 for t in tot if t <= 30)}/{n} "
              f"({sum(1 for t in tot if t <= 30)/n:.2f})", flush=True)
        print(f"  pass <=40d    {sum(1 for t in tot if t <= 40)}/{n}", flush=True)
        print(f"  pass <=50d    {sum(1 for t in tot if t <= 50)}/{n}", flush=True)
        print(f"  median        {tot[len(tot)//2]}d   fastest {tot[0]}d   slowest {tot[-1]}d", flush=True)
    if br:
        print(f"  breaching starts: {br}", flush=True)
        y = {}
        for s in br:
            y[s[:4]] = y.get(s[:4], 0) + 1
        print(f"  by year: {dict(sorted(y.items()))}", flush=True)
    print("[w5_holdout100] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
