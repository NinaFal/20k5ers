#!/usr/bin/env python3
"""
Confirmation: does risk2.2's advantage survive on windows it was never scored on?

The sweep put risk_per_trade_pct 2.2 at 2 breaches against the baseline's 7 on
63 hard-period starts, McNemar p=0.062. That is the only arm of four that beat
the baseline on total failures — risk1.8 (11) and pos15 (13) were both worse
than the baseline's 10.

That lone-winner pattern is exactly what a lucky draw produces, and this project
has already been burned by it once: the baseline itself showed 0 breaches on the
25 starts it was selected with, then 7 on 100 fresh ones. Adopting risk2.2 on
the strength of the sample that selected it would repeat that mistake precisely.

Two confirmation sets, cheapest first:

  PRE2019  the 37 starts from 2015-2018 in the frozen holdout list. No arm in
           the sweep scored a single trial on them, so they are genuinely
           unseen. The baseline's record there is known and clean: 0/37. This is
           a falsification test, not a fair contest — the baseline cannot lose
           it. If risk2.2 introduces breaches where the baseline has none, that
           settles the question against it immediately and for the cost of 37
           runs.

  FRESH    100 starts on a new seed (20260810), spanning the same 2015-2025
           range. Nothing about these touched any selection step for any config,
           so this is the real verdict and is directly comparable to the
           baseline's 7/100.

Both arms run the baseline too, on identical windows, so the comparison stays
paired rather than leaning on the earlier holdout numbers.

Interpretation, fixed in advance so the result cannot be rationalised after the
fact:
  * risk2.2 replaces the frozen baseline only if it shows FEWER breaches on
    FRESH with no more total failures.
  * If it shows equal or more breaches on FRESH, the sweep result was noise and
    the frozen baseline stands at 2.7%.
  * PRE2019 can only disqualify, never promote.

Run:  uv run python3 backtest/src/w5_confirm_risk22.py
"""
import concurrent.futures, importlib.util, json, random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

SEED = 20260810                      # not 20260728 (canonical), not 20260805 (holdout)
FIRST, LAST = date(2015, 1, 5), date(2025, 6, 17)
FRESH_N = 100
FRESH_FILE = w5.DOE_DIR / "CONFIRM_100_STARTS.json"
OUT = w5.W5_DIR / "confirm_risk22.json"

ARMS = {"baseline": {}, "risk2.2": {"__tp__": {"risk_per_trade_pct": 2.2}}}


def pre2019():
    return [s for s in json.loads(
        (w5.DOE_DIR / "HOLDOUT_100_STARTS_2015.json").read_text())["starts"]
        if s[:4] < "2019"]


def fresh():
    if FRESH_FILE.exists():
        return json.loads(FRESH_FILE.read_text())["starts"]
    old = set(json.loads((w5.DOE_DIR / "HOLDOUT_100_STARTS_2015.json").read_text())["starts"])
    rng = random.Random(SEED); span = (LAST - FIRST).days; seen = set()
    while len(seen) < FRESH_N:
        dt = FIRST + timedelta(days=rng.randint(0, span))
        if dt.weekday() < 5 and dt.isoformat() not in old:   # disjoint from holdout
            seen.add(dt.isoformat())
    ss = sorted(seen)
    w5.atomic_write(FRESH_FILE, {"seed": SEED, "n": FRESH_N, "starts": ss,
                                 "disjoint_from": "HOLDOUT_100_STARTS_2015.json"})
    return ss


def cfg(over):
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    over = dict(over); tp.update(over.pop("__tp__", {})); env.update(over)
    return env, tp


def run_set(name, ss, res):
    for arm, over in ARMS.items():
        env, tp = cfg(over)
        slot = res.setdefault(name, {}).setdefault(arm, {})
        todo = [s for s in ss if s not in slot]
        chunk = max(2, w5.WORKERS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
            for i in range(0, len(todo), chunk):
                futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                        for s in todo[i:i + chunk]}
                for f in concurrent.futures.as_completed(futs):
                    r = f.result(); r.pop("detail", None)
                    slot[futs[f]] = r
                w5.atomic_write(OUT, res)
                print(f"[confirm] {name}/{arm}: {len(slot)}/{len(ss)}", flush=True)
        rows = [slot[s] for s in ss if s in slot]
        br = sum(1 for r in rows if r.get("breach"))
        tot = sorted(r["total"] for r in rows if r.get("total") is not None)
        print(f"[confirm] {name}/{arm:9} breach {br}/{len(rows)}  "
              f"stall {len(rows) - br - len(tot)}  pass {len(tot)}  "
              f"median {tot[len(tot) // 2] if tot else '-'}d", flush=True)


def report(name, ss, res):
    import math
    print(f"\n--- {name} (n={len(ss)}) ---", flush=True)
    slots = res.get(name, {})
    common = [s for s in ss if all(s in slots.get(a, {}) for a in ARMS)]
    for arm in ARMS:
        rows = [slots[arm][s] for s in common]
        if not rows:
            continue
        br = sum(1 for r in rows if r.get("breach"))
        tot = sorted(r["total"] for r in rows if r.get("total") is not None)
        print(f"  {arm:<9} breach {br:>3}  stall {len(rows) - br - len(tot):>3}  "
              f"FAIL {br + len(rows) - br - len(tot):>3}  pass {len(tot):>3}  "
              f"median {tot[len(tot) // 2] if tot else '-'}d  "
              f"<=30d {sum(1 for t in tot if t <= 30)}", flush=True)
    bb = {s for s in common if slots["baseline"][s].get("breach")}
    rb = {s for s in common if slots["risk2.2"][s].get("breach")}
    b, c = len(bb - rb), len(rb - bb); n = b + c
    p = sum(math.comb(n, i) for i in range(0, c + 1)) / 2 ** n if n else 1.0
    print(f"  rescued {b}, introduced {c}, McNemar p={p:.3f}", flush=True)


def main():
    res = w5.load_json(OUT)
    pre, fr = pre2019(), fresh()
    print(f"[confirm] PRE2019 {len(pre)} starts (unseen by every sweep arm)", flush=True)
    run_set("pre2019", pre, res)
    print(f"\n[confirm] FRESH {len(fr)} starts, seed {SEED}, disjoint from the holdout",
          flush=True)
    run_set("fresh", fr, res)
    print("\n" + "=" * 66, flush=True)
    report("pre2019", pre, res)
    report("fresh", fr, res)
    print("\n  Decision rule fixed in advance: risk2.2 replaces the frozen baseline\n"
          "  ONLY on fewer breaches in FRESH with no more total failures.", flush=True)
    print("[w5_confirm_risk22] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
