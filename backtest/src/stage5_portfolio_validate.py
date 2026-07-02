#!/usr/bin/env python3
"""
Stage 5 — Portfolio validation: trials 170 + 148 + 146 at 0.33% risk each.

Simulates running 3 TP ladder configs simultaneously on the same entries,
each at 1/3 of the base risk.  Combined net PnL = sum of the 3 sub-accounts.
All 3 must pass (no account breach) for a window to pass.

Usage:
    python -u backtest/src/stage5_portfolio_validate.py
"""
import concurrent.futures
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import doe_harness as dh
from stage4_validate import WINNER_ENV, WINNER_ENTRY

DOE_DIR     = REPO / "backtest" / "output" / "doe"
REPORT_PATH = DOE_DIR / "stage5_portfolio_report.txt"

os.environ.setdefault("RUN_TIMEOUT_S", "999999")
WORKERS = int(os.getenv("VAL_WORKERS", "4"))

RISK = 0.33  # each config's risk per trade (3 × 0.33% ≈ 1% total)

CONFIGS = {
    "trial_170": {
        "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.6,  "tp3_r_multiple": 2.8,
        "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.3,
        "tp1_close_pct":  0.10, "tp2_close_pct":  0.30, "tp3_close_pct": 0.20,
        "tp4_close_pct":  0.15, "tp5_close_pct":  0.25,
        "sl_after_tp2_r": 0.70, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.00,
        "risk_per_trade_pct": RISK,
    },
    "trial_148": {
        "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.7,  "tp3_r_multiple": 2.7,
        "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.6,
        "tp1_close_pct":  0.05, "tp2_close_pct":  0.25, "tp3_close_pct": 0.25,
        "tp4_close_pct":  0.05, "tp5_close_pct":  0.40,
        "sl_after_tp2_r": 0.90, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.10,
        "risk_per_trade_pct": RISK,
    },
    "trial_146": {
        "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.7,  "tp3_r_multiple": 2.8,
        "tp4_r_multiple": 3.5,  "tp5_r_multiple": 4.0,
        "tp1_close_pct":  0.10, "tp2_close_pct":  0.25, "tp3_close_pct": 0.20,
        "tp4_close_pct":  0.05, "tp5_close_pct":  0.40,
        "sl_after_tp2_r": 0.80, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.10,
        "risk_per_trade_pct": RISK,
    },
}

TRAIN_WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2019-07-01", "2022-06-30"),
]

OOS_WINDOWS = [
    ("2015-02-01", "2024-12-31"),
    ("2018-01-01", "2024-12-31"),
    ("2021-01-01", "2024-12-31"),
    ("2023-01-01", "2024-12-31"),
]

def _walk_windows():
    wins = []
    y, m = 2015, 1
    while (y, m) <= (2022, 1):
        s = f"{y:04d}-{m:02d}-01"
        e = (date(y, m, 1) + timedelta(days=730))
        e = min(e, date(2024, 12, 31))
        wins.append((s, e.isoformat()))
        m += 3
        if m > 12:
            m -= 12; y += 1
    return wins

WALK_WINDOWS = _walk_windows()


def run_window_all(start: str, end: str):
    out = {}
    for name, params in CONFIGS.items():
        tp = {**WINNER_ENTRY, **params}
        r = dh.run_single(WINNER_ENV, tp, start, end)
        if r is None:
            out[name] = {"failed": True, "net": 0, "max_tdd": 0}
        else:
            out[name] = {
                "failed":  bool(r.get("account_failed")),
                "net":     float(r.get("net_pnl") or 0),
                "max_tdd": float(r.get("max_tdd_pct") or 0),
            }
    combined_net = sum(v["net"] for v in out.values())
    any_breach   = any(v["failed"] for v in out.values())
    worst_tdd    = max(v["max_tdd"] for v in out.values())
    breached_by  = [k for k, v in out.items() if v["failed"]]
    status = f"BREACH({','.join(breached_by)})" if any_breach else "ok"
    print(f"  {start}→{end}  {status:<30}  net={combined_net:>10,.0f}"
          f"  worst_tdd={worst_tdd:.2f}%", flush=True)
    return {"window": f"{start}→{end}", "combined_net": round(combined_net),
            "any_breach": any_breach, "worst_tdd": round(worst_tdd, 2),
            "breached_by": breached_by}


def run_suite(label: str, windows: list):
    print(f"\n── {label} ({len(windows)} windows) ──────────────────────────",
          flush=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(run_window_all, s, e): (s, e) for s, e in windows}
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())
    results.sort(key=lambda r: r["window"])
    pass_n = sum(1 for r in results if not r["any_breach"])
    print(f"  → {pass_n}/{len(results)} pass", flush=True)
    return results


def build_report(train_r, oos_r, walk_r):
    lines = ["=" * 78,
             "Stage 5 — Portfolio Validation (trials 170 + 148 + 146 @ 0.33% each)",
             f"Total risk per trade: {3*RISK:.2f}%  |  Workers: {WORKERS}",
             "=" * 78]

    def suite_block(label, results):
        lines.append(f"\n── {label} ──")
        pass_n = sum(1 for r in results if not r["any_breach"])
        lines.append(f"Pass rate: {pass_n}/{len(results)}")
        for r in results:
            status = "ok" if not r["any_breach"] else f"BREACH"
            lines.append(f"  {r['window']:<37} {status:<8}"
                         f"  net={r['combined_net']:>10,.0f}"
                         f"  worst_tdd={r['worst_tdd']:.2f}%"
                         + (f"  [{','.join(r['breached_by'])}]" if r['breached_by'] else ""))

    suite_block("Train Windows", train_r)
    suite_block("OOS Windows",   oos_r)
    suite_block("Walk-Forward (2yr rolling)", walk_r)

    walk_pass = sum(1 for r in walk_r if not r["any_breach"])
    lines += ["", "── Summary ──",
              f"  Walk-forward portfolio: {walk_pass}/{len(walk_r)} "
              f"({100*walk_pass/len(walk_r):.0f}%)",
              f"  vs single config (trial 170 @ 1.0%): 25/29 (86%)",
              "", "=" * 78, "STAGE5_PORTFOLIO_DONE_MARKER"]
    return "\n".join(lines)


def main():
    DOE_DIR.mkdir(parents=True, exist_ok=True)
    total = len(TRAIN_WINDOWS) + len(OOS_WINDOWS) + len(WALK_WINDOWS)
    print(f"Portfolio validation: {len(CONFIGS)} configs × {total} windows  "
          f"workers={WORKERS}", flush=True)

    train_r = run_suite("Train Windows",        TRAIN_WINDOWS)
    oos_r   = run_suite("OOS Windows",          OOS_WINDOWS)
    walk_r  = run_suite("Walk-Forward",         WALK_WINDOWS)

    report = build_report(train_r, oos_r, walk_r)
    print(f"\n{report}")
    REPORT_PATH.write_text(report)
    print(f"\nReport: {REPORT_PATH}")
    print("STAGE5_PORTFOLIO_DONE_MARKER")


if __name__ == "__main__":
    main()
