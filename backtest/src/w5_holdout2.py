#!/usr/bin/env python3
"""
SECOND out-of-sample holdout: 100 more fresh starts on the frozen baseline.

The first holdout put t65+TDD at 7 breaches, 7 stalls, 86 passes, median 16d
over 100 starts. That is a single sample. This asks the only question that
matters about it: does it reproduce?

The start list (CONFIRM_100_STARTS.json, seed 20260810) was generated and
committed BEFORE any of these results existed, and is filtered to be disjoint
from HOLDOUT_100_STARTS_2015.json. So no window here has influenced any config
decision, and the two samples share no members — this is a genuine replication,
not a re-measurement.

Config is read from BASELINE_t65_tdd_FROZEN.json, unchanged.

What each outcome would mean:
  * ~7 breaches again  -> the rate is a property of the strategy, and the
    planning figure of roughly 1 lost account in 14 attempts is sound.
  * materially fewer    -> the first holdout drew badly and the true rate is
    lower; every risk decision in this round was made against a pessimistic
    number.
  * materially more     -> 7% was optimistic, and the survival work becomes the
    priority rather than a nice-to-have.

No early abort: every start runs to completion so the count is the true count
rather than censored at the first failure.

Run:  uv run python3 backtest/src/w5_holdout2.py
"""
import concurrent.futures, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

STARTS_FILE = w5.DOE_DIR / "CONFIRM_100_STARTS.json"
OUT = w5.W5_DIR / "holdout2.json"


def main():
    starts = json.loads(STARTS_FILE.read_text())["starts"]
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])

    res = w5.load_json(OUT)
    todo = [s for s in starts if s not in res]
    print(f"[h2] {len(starts)} fresh starts {starts[0]}..{starts[-1]} "
          f"| {len(res)} cached, {len(todo)} to run | NO early abort", flush=True)

    chunk = max(2, w5.WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                res[futs[f]] = r
            w5.atomic_write(OUT, res)
            br = sum(1 for v in res.values() if v.get("breach"))
            tot = sorted(v["total"] for v in res.values() if v.get("total") is not None)
            print(f"[h2] {len(res)}/{len(starts)}  breaches {br}  "
                  f"median {tot[len(tot) // 2] if tot else '-'}", flush=True)

    rows = [res[s] for s in starts if s in res]
    br = [s for s in starts if res.get(s, {}).get("breach")]
    tot = sorted(v["total"] for v in rows if v.get("total") is not None)
    stalls = len(rows) - len(br) - len(tot)
    print("\n" + "=" * 66, flush=True)
    print("[h2] SECOND HOLDOUT — frozen baseline, 100 fresh disjoint starts", flush=True)
    print(f"  passed      {len(tot):>3}/100      (first holdout: 86)", flush=True)
    print(f"  breached    {len(br):>3}/100      (first holdout:  7)", flush=True)
    print(f"  stalled     {stalls:>3}/100      (first holdout:  7)", flush=True)
    if tot:
        print(f"  median      {tot[len(tot) // 2]:>3}d       (first holdout: 16d)", flush=True)
        print(f"  <=30d       {sum(1 for t in tot if t <= 30):>3}/100      "
              f"(first holdout: 69)", flush=True)
        print(f"  fastest {tot[0]}d  slowest {tot[-1]}d", flush=True)
    if br:
        y = {}
        for s in br:
            y[s[:4]] = y.get(s[:4], 0) + 1
        print(f"  breaching starts: {br}", flush=True)
        print(f"  by year: {dict(sorted(y.items()))}   "
              f"(first holdout: all 7 in 2019+)", flush=True)
    print("[w5_holdout2] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
