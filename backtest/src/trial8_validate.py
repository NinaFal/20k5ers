#!/usr/bin/env python3
"""
Validate Stage 3 TRIAL 8 (the max-profit TP ladder) through the same OOS /
train / gap / walk-forward gauntlet that the locked trial 68 passed.

Trial 8 won the Stage 3 sweep on raw profit (avg net $107.8K vs trial 68's
$80.5K, +34%) with essentially equal robustness on the TRAINING windows
(maximin $49.1K vs $50.7K, worst TDD 6.67% vs 6.82%).  Its ladder happens to
equal the inherited BASE_TP baseline.  Before locking it we must confirm the
profit edge holds OUT-OF-SAMPLE and stays zero-breach — the roadmap's #1 guard.

This reuses stage4_validate's suite functions unchanged by monkey-patching the
TP ladder and the output paths, so the running robustness job is untouched.

Usage:
  python -u backtest/src/trial8_validate.py --suite all
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import stage4_validate as sv

# Trial 8 TP ladder (== BASE_TP baseline, the profit-best in the Stage 3 sweep)
TRIAL8_LADDER = {
    "tp1_r_multiple": 0.9,  "tp2_r_multiple": 1.7,  "tp3_r_multiple": 2.4,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.7,
    "tp1_close_pct":  0.10, "tp2_close_pct":  0.35, "tp3_close_pct": 0.15,
    "tp4_close_pct":  0.10, "tp5_close_pct":  0.30,
    "sl_after_tp2_r": 0.70, "sl_after_tp3_r": 1.60, "sl_after_tp4_r": 2.00,
    "risk_per_trade_pct": 1.1,
}

# Patch the module: same entry + risk (WINNER_ENV/WINNER_ENTRY), trial-8 ladder.
sv.WINNER_LADDER = TRIAL8_LADDER
sv.WINNER_TP = {**sv.WINNER_ENTRY, **TRIAL8_LADDER}

# Separate output so we never clobber the locked-config validation artifacts.
sv.RESULTS_PATH = sv.DOE_DIR / "trial8_validation.json"
sv.REPORT_PATH = sv.DOE_DIR / "trial8_validation_report.txt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="all",
                    choices=["all", "oos", "train", "gap", "walk"])
    args = ap.parse_args()

    sv.DOE_DIR.mkdir(parents=True, exist_ok=True)
    results = sv.load_results()
    run_all = args.suite == "all"

    print(f"[{sv.ts()}] TRIAL-8 validation — ladder "
          f"{TRIAL8_LADDER['tp1_r_multiple']}/{TRIAL8_LADDER['tp2_r_multiple']}/"
          f"{TRIAL8_LADDER['tp3_r_multiple']}/{TRIAL8_LADDER['tp4_r_multiple']}/"
          f"{TRIAL8_LADDER['tp5_r_multiple']}R")

    if run_all or args.suite == "oos":
        results = sv.suite_oos(results)
    if run_all or args.suite == "train":
        results = sv.suite_train(results)
    if run_all or args.suite == "gap":
        results = sv.suite_gap(results)
    if run_all or args.suite == "walk":
        results = sv.suite_walk(results)

    report = sv.build_report(results).replace(
        "Locked Stage 1+2+3 Config", "TRIAL 8 (max-profit ladder) — OOS validation")
    print(f"\n{report}")
    sv.REPORT_PATH.write_text(report)
    sv.save_results(results)
    print(f"\n[{sv.ts()}] Results: {sv.RESULTS_PATH}")
    print("TRIAL8_VALIDATION_DONE_MARKER")


if __name__ == "__main__":
    main()
