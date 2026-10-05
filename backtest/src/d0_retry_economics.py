#!/usr/bin/env python3
"""
D0a — retry economics: expected time-to-funded INCLUDING re-takes.

Reframing (WALL3_RD_PLAN.md): a 5%ers breach costs a re-take fee + time, not
the account. So the right objective is not "0% breach" but P(funded within T
days) allowing re-takes. A hotter config that passes fast but breaches ~30% of
attempts can dominate the 0-breach/52-day config on this metric.

Monte-Carlo over the EMPIRICAL per-start outcome distributions already
computed by the C1-wall3 grids (no new backtests):
  - stageC1_wall3_month.json : 16 configs, 60d/step horizon (primary)
  - stageC1_wall3.json       : 24 configs, 40d/step horizon (truncation
    inflates "frozen"; treat funding probs as LOWER bounds)

Outcome model per attempt (drawn i.i.d. from a config's 16 TRAIN starts):
  pass    -> funded after `total` days
  breach  -> lose BREACH_DAY_ASSUMED days (rows don't record the breach day;
             observed range in detailed probes was ~2-21d, so sensitivity
             at 10/15/25), +2 days restart, try again (max 10 attempts)
  frozen  -> attempt drags past the data horizon; counts as NOT funded
             within any evaluated window (conservative)

Reports P(funded <= 30/45/60/90 days) and E[attempts | funded<=90].

Run:  uv run python3 backtest/src/d0_retry_economics.py
"""
import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE = HERE.parent / "output" / "doe"

N_MC = 20_000
MAX_ATTEMPTS = 10
RESTART_DAYS = 2
BREACH_DAY_SENS = [10, 15, 25]
WINDOWS = [30, 45, 60, 90]

random.seed(42)


def load(path):
    d = json.loads((DOE / path).read_text())
    g = defaultdict(list)
    for r in d:
        g[r["config"]].append(r)
    return {k: v for k, v in g.items() if len(v) >= 16}


def outcomes(rows):
    out = []
    for r in rows:
        if r["total"] is not None:
            out.append(("pass", r["total"]))
        elif r["breach"]:
            out.append(("breach", None))
        else:
            out.append(("frozen", None))
    return out


def mc(outc, breach_day):
    """Return {T: P(funded<=T)}, E[attempts | funded<=90]."""
    funded_by = {t: 0 for t in WINDOWS}
    att_sum = att_n = 0
    for _ in range(N_MC):
        t = 0.0
        funded_at = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            kind, days = random.choice(outc)
            if kind == "pass":
                t += days
                funded_at = t
                break
            if kind == "breach":
                t += breach_day + RESTART_DAYS
                continue
            # frozen: attempt never resolves within our measurable horizon
            t = float("inf")
            break
        if funded_at is not None:
            for T in WINDOWS:
                if funded_at <= T:
                    funded_by[T] += 1
            if funded_at <= 90:
                att_sum += attempt
                att_n += 1
    return {T: funded_by[T] / N_MC for T in WINDOWS}, (att_sum / att_n if att_n else None)


def analyze(path, label, note=""):
    print(f"\n=== {label} {note} ===")
    print(f"{'config':>26} {'Bday':>4} {'P<=30':>6} {'P<=45':>6} {'P<=60':>6} {'P<=90':>6} {'E[att]':>6}")
    results = []
    for cfg, rows in sorted(load(path).items()):
        outc = outcomes(rows)
        n_pass = sum(1 for k, _ in outc if k == "pass")
        n_br = sum(1 for k, _ in outc if k == "breach")
        if n_pass == 0:
            continue  # can never fund in-window; skip printing noise
        for bd in BREACH_DAY_SENS:
            p, ea = mc(outc, bd)
            results.append((p[45], cfg, bd, p, ea, n_pass, n_br))
    results.sort(reverse=True)
    for p45, cfg, bd, p, ea, n_pass, n_br in results:
        ea_s = "-" if ea is None else f"{ea:.1f}"
        print(f"{cfg:>26} {bd:>4} {p[30]:>6.2f} {p[45]:>6.2f} {p[60]:>6.2f} {p[90]:>6.2f}"
              f" {ea_s:>6}   (pass {n_pass}/16, breach {n_br}/16)")
    return results


if __name__ == "__main__":
    r1 = analyze("stageC1_wall3_month.json", "60d/step horizon grid (primary)")
    r2 = analyze("stageC1_wall3.json", "40d/step horizon grid",
                 "(LOWER BOUNDS — truncation inflates frozen)")
    print("\n[d0_retry_economics] DONE_MARKER")
