#!/usr/bin/env python3
"""
Safety sweep: which dial actually lowers the breach rate, and what does it cost?

The 100-start holdout put the baseline at 7 breaches, 7 stalls, 86 passes,
median 16d. The goal now is fewer breaches without surrendering the speed that
makes the challenge worth attempting.

Why one dial at a time rather than a grid: the round already produced four
retracted mechanistic claims from small samples, and a 3x2x2 grid at this cost
would take a day to run and still leave every cell underpowered. One-at-a-time
first identifies which lever moves the needle; combining is stage two, on the
lever that actually works.

The dials, and why each is a candidate:

  risk2.2 / risk1.8   risk_per_trade_pct straight down from 2.7. This is the
                      only lever that scales EVERY position simultaneously, and
                      the failure mode is an intrabar gap against aggregate
                      exposure. Most likely to work, most likely to cost speed.
  pos15               MAX_TOTAL_POSITIONS 20 -> 15. Already known decade-CLEAN
                      at $2,618,740, so it survives; unknown whether it lowers
                      the breach RATE across random windows.
  cum5.0              CFG_MAX_CUM_RISK 7.0 -> 5.0. Known to save the 2019 window
                      and known to FAIL 2021 on the decade. Included precisely
                      because that contradiction is unresolved.

Method. All arms run the SAME starts — a paired design, so a difference between
arms cannot be an artifact of which windows each one drew. The starts are the
first N of the frozen 100-start holdout list, which the baseline config was
never tuned on. The baseline is re-run rather than reusing the holdout numbers,
so every arm is measured identically on the identical subset.

Honest limits, stated up front:
  * N=60 resolves large differences, not small ones. Going 7% -> 3% would show;
    7% -> 5% would not. Treat a promising arm as a candidate for confirmation on
    a fresh 100, never as a result.
  * Selecting the best arm on these 60 starts re-creates exactly the winner's
    curse that produced this problem. Any winner here MUST be re-measured on
    starts it was not selected on before it replaces the baseline.

Run:  uv run python3 backtest/src/w5_safety_sweep.py
"""
import concurrent.futures, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

N = 60
OUT = w5.W5_DIR / "safety_sweep.json"

ARMS = {
    "baseline": {},
    "risk2.2":  {"__tp__": {"risk_per_trade_pct": 2.2}},
    "risk1.8":  {"__tp__": {"risk_per_trade_pct": 1.8}},
    "pos15":    {"MAX_TOTAL_POSITIONS": "15"},
    "cum5.0":   {"CFG_MAX_CUM_RISK": "5.0"},
}


def starts():
    f = w5.DOE_DIR / "HOLDOUT_100_STARTS_2015.json"
    return json.loads(f.read_text())["starts"][:N]


def cfg(over):
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    over = dict(over)
    tp.update(over.pop("__tp__", {}))
    env.update(over)
    return env, tp


def main():
    ss = starts()
    res = w5.load_json(OUT)
    print(f"[sweep] {len(ARMS)} arms x {len(ss)} paired starts "
          f"({ss[0]}..{ss[-1]})", flush=True)
    for arm, over in ARMS.items():
        env, tp = cfg(over)
        slot = res.setdefault(arm, {})
        todo = [s for s in ss if s not in slot]
        if todo:
            chunk = max(2, w5.WORKERS)
            with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
                for i in range(0, len(todo), chunk):
                    futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                            for s in todo[i:i + chunk]}
                    for f in concurrent.futures.as_completed(futs):
                        r = f.result(); r.pop("detail", None)
                        slot[futs[f]] = r
                    w5.atomic_write(OUT, res)
                    print(f"[sweep] {arm}: {len(slot)}/{len(ss)}", flush=True)
        rows = [slot[s] for s in ss if s in slot]
        br = sum(1 for r in rows if r.get("breach"))
        tot = sorted(r["total"] for r in rows if r.get("total") is not None)
        stall = len(rows) - br - len(tot)
        print(f"[sweep] {arm:9} breach {br:>2}/{len(rows)}  stall {stall:>2}  "
              f"pass {len(tot):>2}  median {tot[len(tot)//2] if tot else '-'}d  "
              f"<=30d {sum(1 for t in tot if t <= 30)}", flush=True)

    print("\n" + "=" * 74, flush=True)
    print("[sweep] PAIRED — same starts, one dial changed at a time", flush=True)
    print("  {:<10}{:>9}{:>8}{:>7}{:>10}{:>8}".format(
        "arm", "breach", "stall", "pass", "median", "<=30d"), flush=True)
    base = None
    for arm in ARMS:
        slot = res.get(arm) or {}
        rows = [slot[s] for s in ss if s in slot]
        if not rows:
            continue
        br = sum(1 for r in rows if r.get("breach"))
        tot = sorted(r["total"] for r in rows if r.get("total") is not None)
        med = tot[len(tot) // 2] if tot else 0
        p30 = sum(1 for t in tot if t <= 30)
        if arm == "baseline":
            base = (br, med, p30)
        d = ""
        if base and arm != "baseline":
            d = f"   ({br - base[0]:+d} breach, {med - base[1]:+d}d median, {p30 - base[2]:+d} p30)"
        print("  {:<10}{:>9}{:>8}{:>7}{:>9}d{:>8}{}".format(
            arm, f"{br}/{len(rows)}", len(rows) - br - len(tot), len(tot), med, p30, d),
            flush=True)
    print("\n  Any arm that looks better here must be re-measured on starts it was\n"
          "  NOT selected on. Picking the best of five on 60 shared windows is the\n"
          "  same winner's curse that put the baseline at 0/25 and then 7/100.",
          flush=True)
    print("[w5_safety_sweep] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
