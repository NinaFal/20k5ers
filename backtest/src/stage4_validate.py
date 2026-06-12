#!/usr/bin/env python3
"""
Stage 4 — Locked-config validation gauntlet.

Tests the fully locked Stage 1+2+3 configuration against data never seen during
optimization.  Four suites, each written to a separate results section in the
output JSON so the script can be restarted and will skip completed suites.

Suites
------
  oos       5 TEST_STARTS (OOS) + 10-year full run
  train     5 STAGE3 training windows (verify Stage 3 claimed scores reproduce)
  gap       Adverse-slippage sweep 0 → 10 pips on 2022-2024 and 2016-2018
  walk      Rolling 2-year windows every 3 months 2015-01 → 2022-01

Usage
-----
  # Run all suites (may take 2-4 hours total):
  python -u backtest/src/stage4_validate.py

  # Run one suite only:
  python -u backtest/src/stage4_validate.py --suite oos
  python -u backtest/src/stage4_validate.py --suite gap
  python -u backtest/src/stage4_validate.py --suite walk
  python -u backtest/src/stage4_validate.py --suite train

Env vars
--------
  VAL_WORKERS   parallel workers (default 2 — memory-safe for full-path)
  RUN_TIMEOUT_S subprocess timeout in seconds (default 9999 = no timeout)
"""

import argparse
import json
import os
import sys
import time
import concurrent.futures
from pathlib import Path

HERE   = Path(__file__).resolve().parent
REPO   = HERE.parent.parent
sys.path.insert(0, str(HERE))

import doe_harness as dh

# ── Locked Stage 1+2+3 winner config ─────────────────────────────────────────

WINNER_ENV = {
    "RISK_REGIME_ENABLE":    "1",
    "VOL_SIZE_ENABLE":       "0",
    "VOL_REGIME_DD_MULT":    "1.0",
    "RISK_CALM_MULT":        "1.15",
    "RISK_VOLATILE_MULT":    "0.55",
    "VOL_REGIME_DD_OFF":     "2.5",
    "CFG_MAX_CUM_RISK":      "4.0",
    "CFG_DAILY_HALT_PCT":    "2.0",
    "CFG_TDD_CAUTION_PCT":   "4.0",
    "CFG_TDD_WARNING_PCT":   "5.5",
    "CFG_TDD_EMERGENCY_PCT": "8.0",
    "CFG_RISK_CAUTIOUS":     "0.30",
    "CFG_RISK_CONSERVATIVE": "0.25",
    "CFG_RISK_ULTRASAFE":    "0.15",
    "TDD_WALL_SAFETY":       "5.0",
}

# Locked Stage 1 entry (PINNED_ENTRY + ENTRY_A)
WINNER_ENTRY = {
    "trend_min_confluence":    6,
    "range_min_confluence":    3,
    "min_quality_factors":     3,
    "atr_min_percentile":      41.0,
    "atr_vol_ratio_range":     1.4,
    "use_fib_filter":          False,
    "fib_zone_type":           "golden_only",
    "entry_limit_offset_atr":  0.0,
    "entry_fib_level":         0.55,
    "entry_fib_level_volatile": 0.80,
    "fib_vol_ratio_threshold": 1.05,
    "use_trend_quality_gate":  False,
    "adx_min_entry":           0.0,
}

# Locked Stage 3 TP ladder (trial 68)
WINNER_LADDER = {
    "tp1_r_multiple": 0.7,  "tp2_r_multiple": 1.6,  "tp3_r_multiple": 2.7,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 5.5,
    "tp1_close_pct":  0.15, "tp2_close_pct":  0.20, "tp3_close_pct": 0.15,
    "tp4_close_pct":  0.05, "tp5_close_pct":  0.45,
    "sl_after_tp2_r": 0.60, "sl_after_tp3_r": 1.50, "sl_after_tp4_r": 1.90,
    "risk_per_trade_pct": 1.1,
}

WINNER_TP = {**WINNER_ENTRY, **WINNER_LADDER}

# ── Window definitions ────────────────────────────────────────────────────────

# OOS: never seen during any optimization stage
OOS_STARTS = [
    "2015-02-01",   # post-SNB
    "2018-01-01",   # USD strength year
    "2021-01-01",   # post-COVID bull run
    "2023-01-01",   # recent normalisation
    "2023-07-01",   # second half 2023
]
FULL_START = "2015-01-01"
FULL_END   = "2024-12-31"

# Training windows used in Stage 3 (for reproducibility check)
TRAIN_WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2019-07-01", "2022-06-30"),
]

# Gap stress: most demanding windows from Stage 3 + full path
GAP_WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
]
GAP_SLIPPAGE_LEVELS = [0.5, 1.0, 2.0, 5.0, 10.0]

# Walk-forward: rolling 2-year horizons, step = 3 months
WALK_STEP_MONTHS = 3
WALK_HORIZON_DAYS = 730
WALK_FIRST = "2015-01-01"
WALK_LAST  = "2022-01-01"  # last start → end = 2024-01-01, inside data range

# Output
DOE_DIR     = REPO / "backtest" / "output" / "doe"
RESULTS_PATH = DOE_DIR / "stage4_validation.json"
REPORT_PATH  = DOE_DIR / "stage4_validation_report.txt"

WORKERS = int(os.getenv("VAL_WORKERS", "2"))

# Disable run timeout for validation (let long runs finish)
os.environ.setdefault("RUN_TIMEOUT_S", "9999")


# ── Helpers ───────────────────────────────────────────────────────────────────

def ts():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_results() -> dict:
    if RESULTS_PATH.exists():
        try:
            return json.loads(RESULTS_PATH.read_text())
        except Exception:
            pass
    return {}


def save_results(results: dict):
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))


def run_one(env_over, tp_over, start, end=FULL_END):
    r = dh.run_single(env_over, tp_over, start, end)
    a = dh.extract_attrs(r)
    return {"start": start, "end": end, **a}


def month_starts(first: str, last: str, step: int):
    from datetime import date
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}-01")
        m += step
        while m > 12:
            m -= 12
            y += 1
    return out


def horizon_end(start: str, days: int) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(start) + timedelta(days=days)
    if d > date.fromisoformat(FULL_END):
        d = date.fromisoformat(FULL_END)
    return d.isoformat()


def pct_pass(items, key="failed"):
    total = len(items)
    if total == 0:
        return "0/0 (n/a)"
    passed = sum(1 for x in items if not x.get(key, True))
    return f"{passed}/{total} ({100*passed/total:.0f}%)"


def fmt_row(label, a):
    status = "BREACH" if a.get("failed") else "ok"
    net    = a.get("net", 0)
    tdd    = a.get("max_tdd", 0)
    ddd    = a.get("max_ddd", 0)
    scaled = a.get("scalings", 0)
    return (f"  {label:<28} {status:<8} net={net:>10,.0f}  "
            f"tdd={tdd:>5.2f}%  ddd={ddd:>5.2f}%  scalings={scaled}")


# ── Suite: OOS ────────────────────────────────────────────────────────────────

def suite_oos(results: dict) -> dict:
    if "oos" in results:
        print(f"[{ts()}] [oos] already done — skipping")
        return results

    print(f"\n[{ts()}] ── OOS Gauntlet ({'5 OOS + 1 FULL'}) ──────────────────")
    tasks = [(s, FULL_END) for s in OOS_STARTS] + [(FULL_START, FULL_END)]
    out = []

    def _run(args):
        s, e = args
        print(f"[{ts()}] [oos] START {s} → {e}")
        r = run_one(WINNER_ENV, WINNER_TP, s, e)
        print(f"[{ts()}] [oos] DONE  {s}  {'BREACH' if r['failed'] else 'ok'}"
              f"  net={r.get('net',0):,.0f}  tdd={r.get('max_tdd',0):.2f}%")
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(_run, tasks):
            out.append(r)
            results["oos"] = out
            save_results(results)

    return results


# ── Suite: Train verify ───────────────────────────────────────────────────────

def suite_train(results: dict) -> dict:
    if "train" in results:
        print(f"[{ts()}] [train] already done — skipping")
        return results

    print(f"\n[{ts()}] ── Train window re-check ({len(TRAIN_WINDOWS)} windows) ──")
    out = []

    def _run(w):
        s, e = w
        print(f"[{ts()}] [train] START {s} → {e}")
        r = run_one(WINNER_ENV, WINNER_TP, s, e)
        print(f"[{ts()}] [train] DONE  {s}  {'BREACH' if r['failed'] else 'ok'}"
              f"  net={r.get('net',0):,.0f}  tdd={r.get('max_tdd',0):.2f}%")
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(_run, TRAIN_WINDOWS):
            out.append(r)
            results["train"] = out
            save_results(results)

    return results


# ── Suite: Gap stress ─────────────────────────────────────────────────────────

def suite_gap(results: dict) -> dict:
    if "gap" in results:
        print(f"[{ts()}] [gap] already done — skipping")
        return results

    print(f"\n[{ts()}] ── Gap / Slippage Stress ──────────────────────────────")
    out = []

    for (ws, we) in GAP_WINDOWS:
        for slip in GAP_SLIPPAGE_LEVELS:
            key = f"{ws}/{slip}"
            print(f"[{ts()}] [gap] {ws}..{we}  slip={slip} pips")
            env = {**WINNER_ENV, "SLIPPAGE_PIPS": str(slip)}
            r = run_one(env, WINNER_TP, ws, we)
            r["slippage_pips"] = slip
            print(f"[{ts()}] [gap] {ws}  slip={slip}  "
                  f"{'BREACH' if r['failed'] else 'ok'}"
                  f"  net={r.get('net',0):,.0f}  ddd={r.get('max_ddd',0):.2f}%")
            out.append(r)
            results["gap"] = out
            save_results(results)

    return results


# ── Suite: Walk-forward ───────────────────────────────────────────────────────

def suite_walk(results: dict) -> dict:
    if "walk" in results:
        print(f"[{ts()}] [walk] already done — skipping")
        return results

    starts = month_starts(WALK_FIRST, WALK_LAST, WALK_STEP_MONTHS)
    print(f"\n[{ts()}] ── Walk-Forward ({len(starts)} windows, "
          f"{WALK_HORIZON_DAYS}d horizon, step={WALK_STEP_MONTHS}mo) ──────────")
    out = []

    def _run(s):
        e = horizon_end(s, WALK_HORIZON_DAYS)
        print(f"[{ts()}] [walk] START {s} → {e}")
        r = run_one(WINNER_ENV, WINNER_TP, s, e)
        print(f"[{ts()}] [walk] DONE  {s}  {'BREACH' if r['failed'] else 'ok'}"
              f"  net={r.get('net',0):,.0f}  tdd={r.get('max_tdd',0):.2f}%")
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(_run, starts):
            out.append(r)
            results["walk"] = out
            save_results(results)

    return results


# ── Report ────────────────────────────────────────────────────────────────────

def build_report(results: dict) -> str:
    lines = ["=" * 78,
             "Stage 4 Validation Report — Locked Stage 1+2+3 Config",
             f"Generated: {ts()}",
             "=" * 78]

    # OOS
    if "oos" in results:
        oos = results["oos"]
        lines += ["", "── OOS Gauntlet ──────────────────────────────────────────",
                  f"Pass rate: {pct_pass(oos)}  (5 OOS + 1 full 10-yr)"]
        for r in oos:
            label = r["start"] + (" [FULL]" if r["start"] == FULL_START else " [OOS]")
            lines.append(fmt_row(label, r))
        oos_nets = [r["net"] for r in oos if not r.get("failed")]
        if oos_nets:
            lines.append(f"  OOS net P&L range: ${min(oos_nets):,.0f} .. ${max(oos_nets):,.0f}  "
                         f"avg=${sum(oos_nets)/len(oos_nets):,.0f}")

    # Train verify
    if "train" in results:
        tr = results["train"]
        lines += ["", "── Train Window Re-check ─────────────────────────────────",
                  f"Pass rate: {pct_pass(tr)}"]
        for r in tr:
            lines.append(fmt_row(f"{r['start']}..{r['end']}", r))
        tr_nets = [r["net"] for r in tr if not r.get("failed")]
        if tr_nets:
            lines.append(f"  Worst net (maximin): ${min(tr_nets):,.0f}  "
                         f"avg=${sum(tr_nets)/len(tr_nets):,.0f}")

    # Gap stress
    if "gap" in results:
        gap = results["gap"]
        lines += ["", "── Gap / Slippage Stress ─────────────────────────────────",
                  f"{'Window':<26} {'slip(pips)':>10} {'outcome':>8} "
                  f"{'maxDDD%':>8} {'net':>12}"]
        for r in gap:
            status = "BREACH" if r.get("failed") else "ok"
            lines.append(f"  {r['start']:<24} {r.get('slippage_pips',0):>10}  "
                         f"{status:>8}  {r.get('max_ddd',0):>7.2f}  "
                         f"{r.get('net',0):>12,.0f}")
        first_breach = next(
            (r for r in sorted(gap, key=lambda x: x.get("slippage_pips", 0))
             if r.get("failed")), None)
        if first_breach:
            lines.append(f"  First breach: {first_breach['start']} "
                         f"at {first_breach['slippage_pips']} pips")
        else:
            lines.append("  No breach at any tested slippage level.")

    # Walk-forward
    if "walk" in results:
        walk = results["walk"]
        lines += ["", "── Walk-Forward Survival ─────────────────────────────────",
                  f"Pass rate: {pct_pass(walk)}  "
                  f"({WALK_HORIZON_DAYS}d horizon, step={WALK_STEP_MONTHS}mo)"]
        survived = [r for r in walk if not r.get("failed")]
        breached = [r for r in walk if r.get("failed")]
        if survived:
            nets = [r["net"] for r in survived]
            lines.append(f"  Survived  {len(survived):3d}  net: "
                         f"${min(nets):,.0f} .. ${max(nets):,.0f}  "
                         f"avg=${sum(nets)/len(nets):,.0f}")
        if breached:
            lines.append(f"  Breached  {len(breached):3d}  starts: "
                         + ", ".join(r["start"] for r in breached[:8])
                         + ("..." if len(breached) > 8 else ""))

    lines += ["", "=" * 78, "STAGE4_VALIDATION_DONE_MARKER"]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="all",
                    choices=["all", "oos", "train", "gap", "walk"],
                    help="which suite to run (default: all)")
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)
    results = load_results()

    run_all = args.suite == "all"

    if run_all or args.suite == "oos":
        results = suite_oos(results)
    if run_all or args.suite == "train":
        results = suite_train(results)
    if run_all or args.suite == "gap":
        results = suite_gap(results)
    if run_all or args.suite == "walk":
        results = suite_walk(results)

    report = build_report(results)
    print(f"\n{report}")
    REPORT_PATH.write_text(report)
    save_results(results)
    print(f"\n[{ts()}] Results: {RESULTS_PATH}")
    print(f"[{ts()}] Report:  {REPORT_PATH}")
    print(f"[{ts()}] STAGE4_VALIDATION_DONE_MARKER")


if __name__ == "__main__":
    main()
