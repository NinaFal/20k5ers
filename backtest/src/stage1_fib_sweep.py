#!/usr/bin/env python3
"""
Stage 1: Entry / Fib / Frequency sweep

Goal: find entry-parameter settings that maximise win-rate and trade frequency
while surviving the 5 train starts breach-free. This directly addresses the
root failure exposed by the CHF-excluded run: the bot stalls at ~23 trades/year
once the drawdown ladder trips, making recovery impossible.

Architecture (two phases):

  Phase 1a — OAT (One-At-a-Time) screen
    Single start (2016-01-01 → 2018-12-31, 3-year window) for speed.
    Each entry/fib variable swept at 4-5 levels, everything else at BASE.
    Output: sensitivity table — which variables move the needle and in what
    direction. Dead variables are dropped before Phase 1b.

  Phase 1b — Optuna maximin sweep
    Top impactful variables from OAT swept jointly.
    Scored on all 5 TRAIN_STARTS (worst-first early-exit on breach).
    Objective = maximin: maximise min(net_pnl) across survived starts.
    Resumable via SQLite. Run multiple times or with --jobs 2 for speed.

  Phase 1c — Top-5 validation
    Best-5 Optuna configs validated on TEST_STARTS + full 10yr.
    Results written to backtest/output/doe/stage1_top5.json.

Usage:
  uv run python backtest/src/stage1_fib_sweep.py --phase oat
  uv run python backtest/src/stage1_fib_sweep.py --phase optuna --trials 60
  uv run python backtest/src/stage1_fib_sweep.py --phase validate
  uv run python backtest/src/stage1_fib_sweep.py --phase all --trials 60
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent

# Load doe_harness without requiring it to be installed as a package
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR      = dh.DOE_DIR
OAT_CSV      = DOE_DIR / "stage1_oat.csv"
OPTUNA_DB    = DOE_DIR / "stage1_fib.db"
TOP5_JSON    = DOE_DIR / "stage1_top5.json"
OAT_WIN_END  = "2018-12-31"   # 3-year OAT screening window
OAT_START    = "2016-01-01"

# ── Phase 1a: OAT variable grid ───────────────────────────────────────────────
# Each entry is (param_name, is_opt_params, [levels])
# is_opt_params=True → injected via OPT_PARAMS (strategy params)
# is_opt_params=False → injected as env var (not used in Stage 1; placeholder)

OAT_VARS = [
    # Core frequency/quality gate
    ("min_confluence",        True,  [4, 5, 6, 7, 8]),
    ("min_quality_factors",   True,  [2, 3, 4, 5]),
    # Fib entry price placement
    ("entry_fib_level",       True,  [0.500, 0.550, 0.618, 0.700, 0.786]),
    ("entry_limit_offset_atr",True,  [0.0, 0.1, 0.2, 0.3]),
    # Volatility filter
    ("atr_min_percentile",    True,  [30.0, 35.0, 41.0, 47.0, 53.0]),
    ("atr_vol_ratio_range",   True,  [0.7, 0.9, 1.1, 1.4, 1.6]),
    # HTF fib zone filter (now properly wired after the strategy_core fix)
    ("use_fib_filter",        True,  [False, True]),
    ("fib_zone_type",         True,  ["full_retracement", "extended", "golden_only"]),
]

# Base entry params (current_params.json values, kept as OAT baseline)
BASE_ENTRY = {
    "min_confluence":         6,
    "min_quality_factors":    4,
    "entry_fib_level":        0.636,
    "entry_limit_offset_atr": 0.0,
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
}


def _run_oat_config(tp_override: dict) -> dict | None:
    """Run one OAT config on the 3yr screening window."""
    return dh.run_single({}, tp_override, OAT_START, OAT_WIN_END)


def phase_oat():
    """Phase 1a: One-At-a-Time sensitivity screen."""
    print(f"\n{'='*70}")
    print(f"  Stage 1 / Phase 1a: OAT sensitivity screen")
    print(f"  Window: {OAT_START} → {OAT_WIN_END}  (3-year fast screen)")
    print(f"{'='*70}\n")

    rows = []
    header = ["variable", "level", "net_pnl", "max_tdd", "win_rate",
              "trades", "failed", "late_monthly"]

    for var_name, is_tp, levels in OAT_VARS:
        print(f"  ── {var_name} ──")
        for level in levels:
            tp_over = dict(BASE_ENTRY)
            tp_over[var_name] = level
            # fib_zone_type only relevant when use_fib_filter=True
            if var_name == "fib_zone_type":
                tp_over["use_fib_filter"] = True

            t0 = time.time()
            r = _run_oat_config(tp_over)
            elapsed = time.time() - t0
            a = dh.extract_attrs(r)
            lma = dh.late_monthly_avg(r)

            status = "BREACH" if a["failed"] else "OK"
            print(f"    {str(level):<22} {status:<7} net={a['net']:>9,}  "
                  f"tdd={a['max_tdd']:>5.2f}%  wr={a['win_rate']:>5.1f}%  "
                  f"trades={a['trades']:>4}  {elapsed:.0f}s")

            rows.append([var_name, level, a["net"], a["max_tdd"],
                         a["win_rate"], a["trades"], a["failed"], round(lma)])

    with open(OAT_CSV, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

    print(f"\n  OAT results saved → {OAT_CSV}")
    _print_oat_summary(rows)


def _print_oat_summary(rows):
    """Print a ranked sensitivity table from OAT rows."""
    from collections import defaultdict
    by_var = defaultdict(list)
    for r in rows:
        by_var[r[0]].append((r[1], r[2]))   # (level, net_pnl)

    print(f"\n{'─'*60}")
    print(f"  OAT Sensitivity Summary  (range of net_pnl per variable)")
    print(f"{'─'*60}")
    ranked = []
    for var, results in by_var.items():
        nets = [x[1] for x in results]
        rng = max(nets) - min(nets)
        best_level = results[nets.index(max(nets))][0]
        ranked.append((rng, var, best_level, max(nets), min(nets)))
    ranked.sort(reverse=True)
    for rng, var, best, hi, lo in ranked:
        print(f"  {var:<30}  range={rng:>9,}  "
              f"best={str(best):<22}  [{lo:,} → {hi:,}]")
    print()


# ── Phase 1b: Optuna maximin sweep ────────────────────────────────────────────

def _build_entry_params(trial: optuna.Trial) -> dict:
    """Suggest entry/fib params for one Optuna trial."""
    return {
        "min_confluence":         trial.suggest_int("min_confluence", 4, 8),
        "min_quality_factors":    trial.suggest_int("min_quality_factors", 2, 5),
        "entry_fib_level":        trial.suggest_float("entry_fib_level",
                                                       0.50, 0.786, step=0.025),
        "entry_limit_offset_atr": trial.suggest_float("entry_limit_offset_atr",
                                                       0.0, 0.35, step=0.05),
        "atr_min_percentile":     trial.suggest_float("atr_min_percentile",
                                                       28.0, 55.0, step=2.5),
        "atr_vol_ratio_range":    trial.suggest_float("atr_vol_ratio_range",
                                                       0.7, 1.6, step=0.1),
        "use_fib_filter":         trial.suggest_categorical("use_fib_filter",
                                                             [False, True]),
        "fib_zone_type":          trial.suggest_categorical("fib_zone_type",
                                                             ["full_retracement",
                                                              "extended",
                                                              "golden_only"]),
    }


def _optuna_objective(trial: optuna.Trial) -> float:
    """
    Maximin objective: max min(net_pnl) across all 5 train starts.
    Uses early-exit: first breach on any killer start ends the trial.
    """
    entry = _build_entry_params(trial)

    # Phase 1: killer starts (cheap early-exit)
    for start in dh.KILLER_STARTS:
        r = dh.run_single({}, entry, start)
        a = dh.extract_attrs(r)
        trial.set_user_attr(f"net_{start[:7]}", a["net"])
        trial.set_user_attr(f"tdd_{start[:7]}", a["max_tdd"])
        trial.set_user_attr(f"wr_{start[:7]}", a["win_rate"])
        if a["failed"]:
            trial.set_user_attr("fail_start", start)
            trial.set_user_attr("breach_type", a["breach_type"])
            return -1e9 + float(a["survived_days"]) * 100

    # Phase 2: all 5 train starts (survivors only)
    nets = []
    for start in dh.TRAIN_STARTS:
        if start in dh.KILLER_STARTS:
            # Already ran above — re-use cached attr
            net = trial.user_attrs.get(f"net_{start[:7]}", None)
            if net is None:
                r = dh.run_single({}, entry, start)
                a = dh.extract_attrs(r)
                net = a["net"]
        else:
            r = dh.run_single({}, entry, start)
            a = dh.extract_attrs(r)
            if a["failed"]:
                trial.set_user_attr("fail_start", start)
                trial.set_user_attr("breach_type", a["breach_type"])
                return -1e9 + float(a["survived_days"]) * 100
            trial.set_user_attr(f"net_{start[:7]}", a["net"])
            trial.set_user_attr(f"wr_{start[:7]}", a["win_rate"])
            net = a["net"]
        nets.append(net)

    trial.set_user_attr("entry_params", entry)
    trial.set_user_attr("maximin", int(min(nets)))
    return float(min(nets))


def phase_optuna(n_trials: int, study_name: str = "stage1_fib"):
    """Phase 1b: Optuna maximin sweep over entry/fib parameters."""
    storage = f"sqlite:///{OPTUNA_DB}"
    study = optuna.create_study(
        study_name=study_name, storage=storage,
        direction="maximize", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42, n_startup_trials=15),
    )
    completed = len([t for t in study.trials
                     if t.state == optuna.trial.TrialState.COMPLETE])
    print(f"\n{'='*70}")
    print(f"  Stage 1 / Phase 1b: Optuna maximin sweep")
    print(f"  DB: {OPTUNA_DB}")
    print(f"  Existing completed trials: {completed}  /  requesting: {n_trials}")
    print(f"  Train starts: {dh.TRAIN_STARTS}")
    print(f"{'='*70}\n")
    study.optimize(_optuna_objective, n_trials=n_trials, show_progress_bar=True)
    _print_optuna_summary(study)


def _print_optuna_summary(study: optuna.Study):
    trials = [t for t in study.trials
              if t.state == optuna.trial.TrialState.COMPLETE and t.value > -1e8]
    if not trials:
        print("  No non-breaching trials yet.\n")
        return
    trials.sort(key=lambda t: t.value, reverse=True)
    print(f"\n  Top-10 non-breaching trials (maximin score = worst-start net P&L):")
    print(f"  {'#':<4} {'score':>10}  params")
    for i, t in enumerate(trials[:10]):
        params_str = "  ".join(f"{k}={v}" for k, v in t.params.items())
        print(f"  {i+1:<4} {t.value:>10,.0f}  {params_str}")
    print()


# ── Phase 1c: validate top-5 ─────────────────────────────────────────────────

def phase_validate(n_top: int = 5):
    """Phase 1c: run top-N configs on TEST_STARTS + full 10yr."""
    if not OPTUNA_DB.exists():
        print("  No Optuna DB found — run phase optuna first."); return

    study = optuna.load_study(
        study_name="stage1_fib",
        storage=f"sqlite:///{OPTUNA_DB}",
    )
    trials = [t for t in study.trials
              if t.state == optuna.trial.TrialState.COMPLETE and t.value > -1e8]
    if not trials:
        print("  No non-breaching trials yet."); return
    trials.sort(key=lambda t: t.value, reverse=True)
    top = trials[:n_top]

    configs = []
    for i, t in enumerate(top):
        ep = t.user_attrs.get("entry_params") or t.params
        configs.append({
            "label":    f"stage1_top{i+1}_trial{t.number}",
            "env":      {},          # entry params go via OPT_PARAMS
            "tp":       ep,          # merged into BASE_TP inside run_single
            "train_score": t.value,
        })

    validated = dh.validate_configs(configs, tag="stage1_top5")
    TOP5_JSON.write_text(json.dumps(validated, indent=2, default=str))
    print(f"\n  Top-{n_top} validation results saved → {TOP5_JSON}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Stage 1 fib sweep")
    p.add_argument("--phase", choices=["oat", "optuna", "validate", "all"],
                   default="all")
    p.add_argument("--trials", type=int, default=60,
                   help="Number of Optuna trials (phase optuna / all)")
    args = p.parse_args()

    # Ensure tmp dir exists
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    if args.phase in ("oat", "all"):
        phase_oat()
    if args.phase in ("optuna", "all"):
        phase_optuna(args.trials)
    if args.phase in ("validate", "all"):
        phase_validate()


if __name__ == "__main__":
    main()
