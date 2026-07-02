#!/usr/bin/env python3
"""
Stage 4 — Post-sweep perturbation robustness check.

For each of the top-K Pareto configs, runs all 5 training windows at
risk=0.8%, 0.9%, and 1.0%.  Identifies configs that are safe at 1.0%
(ideal) or at least robust at 0.9% with margin at 0.8%.

Usage:
  python -u backtest/src/stage4_perturb_validate.py [--top K]

Env vars:
  VAL_WORKERS   parallel workers (default 4)
  RUN_TIMEOUT_S subprocess timeout (default 999999)
"""

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import optuna
from optuna.trial import TrialState
optuna.logging.set_verbosity(optuna.logging.WARNING)

import doe_harness as dh
from stage4_validate import WINNER_ENV, WINNER_ENTRY, TRAIN_WINDOWS

DOE_DIR     = REPO / "backtest" / "output" / "doe"
DB_PATH     = DOE_DIR / "stage4_pareto.db"
REPORT_PATH = DOE_DIR / "stage4_perturb_report.txt"

RISK_LEVELS = [0.8, 0.9, 1.0]
WORKERS     = int(os.getenv("VAL_WORKERS", "4"))

os.environ.setdefault("RUN_TIMEOUT_S", "999999")


def run_window(params: dict, start: str, end: str):
    tp = {**WINNER_ENTRY, **params}
    return dh.run_single(WINNER_ENV, tp, start, end)


def check_config(trial_num: int, base_params: dict, risk: float):
    """Run all 5 windows for one config at one risk level. Returns summary dict."""
    params = dict(base_params)
    params["risk_per_trade_pct"] = risk
    results = []
    for (s, e) in TRAIN_WINDOWS:
        r = run_window(params, s, e)
        if r is None:
            results.append({"window": f"{s}→{e}", "failed": True, "net": 0,
                            "max_tdd_pct": 0.0, "error": "infra"})
            continue
        failed = bool(r.get("account_failed"))
        net    = float(r.get("net_pnl") or 0)
        tdd    = float(r.get("max_tdd_pct") or 0)
        results.append({"window": f"{s}→{e}", "failed": failed,
                        "net": net, "max_tdd_pct": tdd})
    breaches = sum(1 for x in results if x["failed"])
    nets     = [x["net"] for x in results if not x["failed"]]
    maximin  = min(nets) if nets else 0.0
    worst_tdd = max(x["max_tdd_pct"] for x in results)
    print(f"  trial={trial_num:3d} risk={risk:.1f}%  "
          f"breaches={breaches}/5  maximin={maximin:>8,.0f}  "
          f"worst_tdd={worst_tdd:.2f}%", flush=True)
    return {
        "trial": trial_num, "risk": risk,
        "breaches": breaches, "maximin": round(maximin),
        "worst_tdd": round(worst_tdd, 2), "windows": results,
    }


def build_report(top_trials, all_results):
    lines = [
        "=" * 78,
        "Stage 4 — Perturbation Robustness Report",
        f"Top {len(top_trials)} configs × {len(RISK_LEVELS)} risk levels "
        f"× 5 training windows",
        "=" * 78, "",
    ]

    for t_num, base_obj, base_wtdd, base_params in top_trials:
        lines.append(f"── Trial #{t_num}  sweep_obj={base_obj:,.0f}  "
                     f"sweep_wtdd={base_wtdd:.2f}%  "
                     f"tp3={base_params.get('tp3_r_multiple')}"
                     f"  tp5={base_params.get('tp5_r_multiple')}"
                     f"  c2={base_params.get('tp2_close_pct')}")
        lines.append(f"  {'risk':>6}  {'breaches':>8}  {'maximin':>10}  "
                     f"{'worst_tdd':>10}  verdict")
        lines.append("  " + "-" * 60)
        for res in all_results.get(t_num, []):
            breaches  = res["breaches"]
            verdict   = "PASS" if breaches == 0 else f"FAIL ({breaches} breach)"
            lines.append(
                f"  {res['risk']:>5.1f}%  {breaches:>8}  "
                f"{res['maximin']:>10,.0f}  {res['worst_tdd']:>9.2f}%  {verdict}")
        lines.append("")

    # Summary: pick candidates that pass at 0.9% AND at 0.8%
    lines.append("── Robustness Summary ────────────────────────────────────────")
    lines.append(f"  {'trial':>6}  {'0.8%':>8}  {'0.9%':>8}  {'1.0%':>8}  "
                 f"{'sweep_obj':>10}  recommendation")
    lines.append("  " + "-" * 72)
    for t_num, base_obj, base_wtdd, _ in top_trials:
        res_by_risk = {r["risk"]: r for r in all_results.get(t_num, [])}
        def verdict(risk):
            r = res_by_risk.get(risk)
            if r is None: return "n/a"
            return "PASS" if r["breaches"] == 0 else f"FAIL"
        v08, v09, v10 = verdict(0.8), verdict(0.9), verdict(1.0)
        if v08 == "PASS" and v09 == "PASS" and v10 == "PASS":
            rec = "IDEAL — safe at all 3 risk levels"
        elif v08 == "PASS" and v09 == "PASS":
            rec = "GOOD  — safe at 0.8% and 0.9%"
        elif v09 == "PASS":
            rec = "OK    — safe at 0.9% only"
        else:
            rec = "WEAK  — fails at 0.9%"
        lines.append(f"  {t_num:>6}  {v08:>8}  {v09:>8}  {v10:>8}  "
                     f"{base_obj:>10,.0f}  {rec}")

    lines += ["", "=" * 78, "STAGE4_PERTURB_DONE_MARKER"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5, help="top-K configs to validate")
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)

    study = optuna.load_study(
        study_name="stage4_pareto",
        storage=f"sqlite:///{DB_PATH}",
    )
    valid = [
        t for t in study.trials
        if t.state == TrialState.COMPLETE
        and t.value is not None and t.value > -1e9
    ]
    valid.sort(key=lambda t: -t.value)
    top_k = valid[:args.top]

    top_trials = []
    for t in top_k:
        params = json.loads(t.user_attrs["params"])
        top_trials.append((
            t.number,
            t.value,
            t.user_attrs.get("worst_tdd", 0.0),
            params,
        ))

    print(f"Validating top {len(top_trials)} configs × "
          f"{len(RISK_LEVELS)} risk levels × 5 windows = "
          f"{len(top_trials)*len(RISK_LEVELS)*5} backtests  "
          f"(workers={WORKERS})")
    print()

    tasks = []
    for (t_num, base_obj, base_wtdd, base_params) in top_trials:
        for risk in RISK_LEVELS:
            tasks.append((t_num, base_params, risk))

    all_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(check_config, t, p, r): (t, r) for (t, p, r) in tasks}
        for fut in concurrent.futures.as_completed(futs):
            t_num, risk = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:
                print(f"  trial={t_num} risk={risk} ERROR: {exc}", flush=True)
                res = {"trial": t_num, "risk": risk, "breaches": 99,
                       "maximin": 0, "worst_tdd": 0, "windows": []}
            all_results.setdefault(t_num, []).append(res)

    # Sort per-trial results by risk level
    for t_num in all_results:
        all_results[t_num].sort(key=lambda r: r["risk"])

    report = build_report(top_trials, all_results)
    print(f"\n{report}")
    REPORT_PATH.write_text(report)
    print(f"\nReport: {REPORT_PATH}")
    print("STAGE4_PERTURB_DONE_MARKER")


if __name__ == "__main__":
    main()
