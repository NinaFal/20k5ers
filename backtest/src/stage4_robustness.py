#!/usr/bin/env python3
"""
Stage 4 — Robustness gauntlet (the 3 tests stage4_validate.py did NOT cover).

Per OPTIMIZATION_ROADMAP.md, a config advances only if it passes the full
validation gauntlet.  stage4_validate.py covered walk-forward/OOS, gap stress,
5-start survival and the 10-year run.  This module adds the remaining three:

  worst   Worst-case intrabar TDD  (TDD_WORST_CASE=1) — does a wick piercing the
          wall mid-bar breach where bar-close equity didn't?
  mc      Monte-Carlo trade-order shuffle — drawdown is path-dependent; the same
          trades in a worse order can breach.  Headline number: P(TDD ≥ 10%).
  perturb Parameter-perturbation robustness — a robust optimum sits on a plateau,
          not a spike.  Nudge each key lever ±1 step and confirm survival holds.

All tests run on the LOCKED Stage 1+2+3 config (imported from stage4_validate).

Usage
-----
  python -u backtest/src/stage4_robustness.py                # all three
  python -u backtest/src/stage4_robustness.py --suite worst
  python -u backtest/src/stage4_robustness.py --suite mc --mc 5000
  python -u backtest/src/stage4_robustness.py --suite perturb

Checkpointed: re-running skips completed suites (stage4_robustness.json).
"""

import argparse
import json
import os
import sys
import subprocess
import tempfile
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BACKTEST = HERE / "main_live_bot_backtest.py"
sys.path.insert(0, str(HERE))

from stage4_validate import (
    WINNER_ENV, WINNER_TP, WINNER_LADDER,
    TRAIN_WINDOWS, FULL_START, FULL_END,
)

DOE_DIR      = REPO / "backtest" / "output" / "doe"
RESULTS_PATH = DOE_DIR / "stage4_robustness.json"
REPORT_PATH  = DOE_DIR / "stage4_robustness_report.txt"

BAL      = 50000.0
WALL_TDD = 10.0   # 5%ers total-drawdown wall
WALL_DDD = 5.0    # 5%ers daily-drawdown wall

os.environ.setdefault("RUN_TIMEOUT_S", "9999")


# ── Engine runner (returns results dict + trades DataFrame) ───────────────────

def run(env_over: dict, params: dict, start: str, end: str):
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    env = dict(os.environ)
    env.update(WINNER_ENV)
    env.update(env_over)
    env["OPT_PARAMS"] = json.dumps(params)
    env["PYTHONUTF8"] = "1"
    cmd = [sys.executable, str(BACKTEST), "--start", start, "--end", end,
           "--balance", str(BAL), "--output", td, "--quiet"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       cwd=str(REPO), encoding="utf-8", errors="replace")
    rj, tj = Path(td) / "results.json", Path(td) / "trades.csv"
    if p.returncode != 0 or not rj.exists():
        return None, None
    res = json.loads(rj.read_text())
    trades = pd.read_csv(tj) if tj.exists() else pd.DataFrame()
    return res, trades


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_results() -> dict:
    if RESULTS_PATH.exists():
        try:
            return json.loads(RESULTS_PATH.read_text())
        except Exception:
            pass
    return {}


def save_results(r: dict):
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(r, indent=2, default=str))


# ── Monte-Carlo helpers (path-dependence) ─────────────────────────────────────

def daily_pnl(trades):
    if trades is None or trades.empty or "close_time" not in trades:
        return pd.Series(dtype=float)
    t = trades.copy()
    t["close_time"] = pd.to_datetime(t["close_time"], utc=True, errors="coerce")
    t = t.dropna(subset=["close_time"])
    t["day"] = t["close_time"].dt.date
    return t.groupby("day")["pnl"].sum().sort_index()


def max_tdd_pct(daily, start_bal):
    eq = start_bal + np.cumsum(daily.values)
    eq = np.concatenate([[start_bal], eq])
    peak = np.maximum.accumulate(eq)
    return float(((peak - eq) / peak * 100.0).max())


def monte_carlo(daily, start_bal, n, seed=42):
    rng = np.random.default_rng(seed)
    vals = daily.values.copy()
    tdds = np.empty(n)
    for i in range(n):
        rng.shuffle(vals)
        eq = start_bal + np.cumsum(vals)
        eq = np.concatenate([[start_bal], eq])
        peak = np.maximum.accumulate(eq)
        tdds[i] = ((peak - eq) / peak * 100.0).max()
    return {
        "p_breach_10pct": float((tdds >= WALL_TDD).mean()),
        "tdd_mean":   float(tdds.mean()),
        "tdd_median": float(np.median(tdds)),
        "tdd_p95":    float(np.percentile(tdds, 95)),
        "tdd_p99":    float(np.percentile(tdds, 99)),
        "tdd_max":    float(tdds.max()),
    }


# ── Suite: worst-case intrabar TDD ────────────────────────────────────────────

def suite_worst(results: dict) -> dict:
    if "worst" in results:
        print(f"[{ts()}] [worst] already done — skipping")
        return results
    print(f"\n[{ts()}] ── Worst-case intrabar TDD (TDD_WORST_CASE=1) ──────────")
    # The 5 training windows + the full 10-year run — the windows that matter.
    windows = list(TRAIN_WINDOWS) + [(FULL_START, FULL_END)]
    out = []
    for (s, e) in windows:
        # baseline (bar-close) and worst-case (intrabar) for direct comparison
        rb, _ = run({}, WINNER_TP, s, e)
        rw, _ = run({"TDD_WORST_CASE": "1"}, WINNER_TP, s, e)
        row = {
            "start": s, "end": e,
            "base_failed":  bool(rb.get("account_failed")) if rb else None,
            "base_tdd":     float(rb.get("max_tdd_pct") or 0) if rb else None,
            "worst_failed": bool(rw.get("account_failed")) if rw else None,
            "worst_tdd":    float(rw.get("max_tdd_pct") or 0) if rw else None,
            "worst_ddd":    float(rw.get("max_ddd_pct") or 0) if rw else None,
            "worst_net":    round(float(rw.get("net_pnl") or 0)) if rw else None,
        }
        out.append(row)
        delta = (row["worst_tdd"] or 0) - (row["base_tdd"] or 0)
        print(f"[{ts()}] [worst] {s}  base_tdd={row['base_tdd']}  "
              f"worst_tdd={row['worst_tdd']}  Δ={delta:+.2f}  "
              f"{'BREACH' if row['worst_failed'] else 'ok'}")
        results["worst"] = out
        save_results(results)
    return results


# ── Suite: Monte-Carlo trade-order shuffle ────────────────────────────────────

def suite_mc(results: dict, n_iter: int) -> dict:
    if "mc" in results:
        print(f"[{ts()}] [mc] already done — skipping")
        return results
    print(f"\n[{ts()}] ── Monte-Carlo trade-order shuffle ({n_iter} shuffles) ──")
    # Long OOS windows give the richest daily-PnL distribution to shuffle.
    mc_windows = [
        ("2018-01-01", "2024-12-31"),   # 7yr OOS
        ("2021-01-01", "2024-12-31"),   # recent regime
        (FULL_START,   FULL_END),       # full 10yr
    ]
    out = []
    for (s, e) in mc_windows:
        res, trades = run({}, WINNER_TP, s, e)
        d = daily_pnl(trades)
        if d.empty:
            print(f"[{ts()}] [mc] {s}: no trades — skip")
            continue
        actual = max_tdd_pct(d, BAL)
        mc = monte_carlo(d, BAL, n_iter)
        row = {"start": s, "end": e, "trading_days": int(len(d)),
               "actual_tdd": actual, **mc}
        out.append(row)
        print(f"[{ts()}] [mc] {s}  actual={actual:.2f}%  mean={mc['tdd_mean']:.2f}%  "
              f"p95={mc['tdd_p95']:.2f}%  p99={mc['tdd_p99']:.2f}%  "
              f"max={mc['tdd_max']:.2f}%  P(breach)={mc['p_breach_10pct']*100:.2f}%")
        results["mc"] = out
        save_results(results)
    return results


# ── Suite: parameter-perturbation robustness ──────────────────────────────────

def _perturbations():
    """Yield (label, env_over, params) for each ±1-step nudge of a key lever.

    Each perturbation changes ONE lever; everything else stays at the locked
    winner.  A robust optimum survives all of these (plateau, not spike).
    """
    base = dict(WINNER_TP)

    # risk-per-trade ±0.1%
    for r in (1.0, 1.2):
        p = dict(base); p["risk_per_trade_pct"] = r
        yield (f"risk={r}", {}, p)

    # SL-trail levels ±0.1R (one at a time)
    for key in ("sl_after_tp2_r", "sl_after_tp3_r", "sl_after_tp4_r"):
        for d in (-0.1, +0.1):
            p = dict(base); p[key] = round(base[key] + d, 2)
            yield (f"{key}{d:+.1f}", {}, p)

    # TP5 R-multiple (the runner) ±0.3R
    for d in (-0.3, +0.3):
        p = dict(base); p["tp5_r_multiple"] = round(base["tp5_r_multiple"] + d, 2)
        yield (f"tp5_r{d:+.1f}", {}, p)

    # TP1 close-fraction ±5% (shift to/from tp5 to keep sum=1)
    for d in (-0.05, +0.05):
        p = dict(base)
        p["tp1_close_pct"] = round(base["tp1_close_pct"] + d, 3)
        p["tp5_close_pct"] = round(base["tp5_close_pct"] - d, 3)
        yield (f"tp1_close{d:+.2f}", {}, p)


def suite_perturb(results: dict) -> dict:
    if "perturb" in results:
        print(f"[{ts()}] [perturb] already done — skipping")
        return results
    print(f"\n[{ts()}] ── Parameter-perturbation robustness ──────────────────")
    perts = list(_perturbations())
    out = []
    for (label, env_over, params) in perts:
        # Score each perturbation on the 5 training windows: worst-window net
        # (maximin) and whether ANY window breaches.
        nets, breached, worst_tdd = [], False, 0.0
        for (s, e) in TRAIN_WINDOWS:
            res, _ = run(env_over, params, s, e)
            if res is None:
                breached = True   # treat infra failure conservatively
                continue
            if res.get("account_failed"):
                breached = True
            nets.append(round(float(res.get("net_pnl") or 0)))
            worst_tdd = max(worst_tdd, float(res.get("max_tdd_pct") or 0))
        row = {"label": label, "breached": breached,
               "maximin_net": min(nets) if nets else None,
               "avg_net": round(sum(nets) / len(nets)) if nets else None,
               "worst_tdd": round(worst_tdd, 2)}
        out.append(row)
        print(f"[{ts()}] [perturb] {label:22}  "
              f"{'BREACH' if breached else 'ok':6}  "
              f"maximin={row['maximin_net']}  worst_tdd={row['worst_tdd']}%")
        results["perturb"] = out
        save_results(results)
    return results


# ── Report ────────────────────────────────────────────────────────────────────

def build_report(results: dict) -> str:
    L = ["=" * 78,
         "Stage 4 Robustness Report — Locked Stage 1+2+3 Config",
         f"Generated: {ts()}",
         "=" * 78]

    if "worst" in results:
        L += ["", "── Worst-Case Intrabar TDD (TDD_WORST_CASE=1) ────────────",
              f"{'window':<24} {'base_tdd':>9} {'worst_tdd':>10} {'Δ':>7} {'outcome':>8}"]
        new_breaches = 0
        for r in results["worst"]:
            d = (r.get("worst_tdd") or 0) - (r.get("base_tdd") or 0)
            outc = "BREACH" if r.get("worst_failed") else "ok"
            if r.get("worst_failed") and not r.get("base_failed"):
                new_breaches += 1
                outc = "NEW-BREACH"
            L.append(f"  {r['start']:<22} {r.get('base_tdd',0):>9} "
                     f"{r.get('worst_tdd',0):>10} {d:>+7.2f} {outc:>8}")
        L.append(f"  Intrabar-only NEW breaches (passed bar-close, failed wick): {new_breaches}")

    if "mc" in results:
        L += ["", "── Monte-Carlo Trade-Order Shuffle (path-dependence) ─────",
              f"{'window':<24} {'actual':>7} {'mean':>7} {'p95':>7} {'p99':>7} "
              f"{'max':>7} {'P(breach)':>10}"]
        for r in results["mc"]:
            L.append(f"  {r['start']:<22} {r.get('actual_tdd',0):>6.2f}% "
                     f"{r.get('tdd_mean',0):>6.2f}% {r.get('tdd_p95',0):>6.2f}% "
                     f"{r.get('tdd_p99',0):>6.2f}% {r.get('tdd_max',0):>6.2f}% "
                     f"{r.get('p_breach_10pct',0)*100:>9.2f}%")
        worst_pb = max((r.get("p_breach_10pct", 0) for r in results["mc"]), default=0)
        L.append(f"  Worst-window P(TDD breaches 10% wall): {worst_pb*100:.2f}%")

    if "perturb" in results:
        L += ["", "── Parameter-Perturbation Robustness (plateau test) ──────",
              f"{'perturbation':<24} {'outcome':>8} {'maximin_net':>12} {'worst_tdd':>10}"]
        n_breach = 0
        for r in results["perturb"]:
            if r.get("breached"):
                n_breach += 1
            L.append(f"  {r['label']:<24} {'BREACH' if r.get('breached') else 'ok':>8} "
                     f"{(r.get('maximin_net') or 0):>12,} {r.get('worst_tdd',0):>9}%")
        L.append(f"  Perturbations that breach: {n_breach}/{len(results['perturb'])}  "
                 f"(robust plateau ⇒ 0)")

    L += ["", "=" * 78, "STAGE4_ROBUSTNESS_DONE_MARKER"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="all",
                    choices=["all", "worst", "mc", "perturb"])
    ap.add_argument("--mc", type=int, default=5000, help="Monte-Carlo iterations")
    args = ap.parse_args()

    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    results = load_results()
    run_all = args.suite == "all"

    if run_all or args.suite == "worst":
        results = suite_worst(results)
    if run_all or args.suite == "mc":
        results = suite_mc(results, args.mc)
    if run_all or args.suite == "perturb":
        results = suite_perturb(results)

    report = build_report(results)
    print(f"\n{report}")
    REPORT_PATH.write_text(report)
    save_results(results)
    print(f"\n[{ts()}] Results: {RESULTS_PATH}")
    print(f"[{ts()}] Report:  {REPORT_PATH}")
    print(f"[{ts()}] STAGE4_ROBUSTNESS_DONE_MARKER")


if __name__ == "__main__":
    main()
