#!/usr/bin/env python3
"""
Stage 1: Entry / Fib / Frequency sweep  (crash-proof, parallel)

Phase 1a — OAT (One-At-a-Time) sensitivity screen
  4 concurrent workers on a 3-year window (2016→2018).
  Skip-if-done: safe to restart mid-run without losing work.
  Results appended row-by-row to stage1_oat.csv.

Phase 1b — Optuna maximin sweep (resumable via SQLite)
  Sweeps the real entry/fib levers jointly over all 5 TRAIN_STARTS.
  Two parallel workers share the same SQLite study — restart-safe.
  Objective = maximin: max min(net_pnl) with hard breach floor.

Phase 1c — Top-5 validation
  Best-5 configs from Optuna validated on TEST_STARTS + full 10yr.
  Written to stage1_top5.json.

Usage (via the supervisor shell script — don't run phases manually):
  bash backtest/src/run_stage1.sh
  # or individual phases:
  uv run python -u backtest/src/stage1_fib_sweep.py --phase oat
  uv run python -u backtest/src/stage1_fib_sweep.py --phase optuna --trials 40
  uv run python -u backtest/src/stage1_fib_sweep.py --phase validate

Key fix vs prior version:
  min_confluence is NOT the real entry gate — the bot uses trend_min_confluence
  and range_min_confluence (selected by ADX regime at line 2519 of strategy_core).
  OAT confirmed: sweeping min_confluence 4-7 gave identical results. Replaced.
"""
import argparse
import concurrent.futures
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
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR     = dh.DOE_DIR
OAT_CSV     = DOE_DIR / "stage1_oat.csv"
OPTUNA_DB   = DOE_DIR / "stage1_fib.db"
TOP5_JSON   = DOE_DIR / "stage1_top5.json"
OAT_START   = "2016-01-01"
OAT_END     = "2018-12-31"   # 3-year screening window (~2 min/run at 4 cores)
OAT_WORKERS = 4              # safe: 4 × 1.5GB = 6GB on a 14GB-free box

# ── OAT variable grid ────────────────────────────────────────────────────────
# NOTE: min_confluence removed — dead lever (bot routes through trend/range_min_confluence).
# OAT confirmed: sweeping 4-7 gave byte-identical results (434 trades each).
OAT_VARS = [
    # Real confluence gates (ADX-regime selected)
    ("trend_min_confluence",  [4, 5, 6, 7, 8]),
    ("range_min_confluence",  [2, 3, 4, 5]),
    ("min_quality_factors",   [2, 3, 4, 5]),
    # Fib entry price placement (entry_fib_level = where limit order sits on the swing)
    ("entry_fib_level",       [0.500, 0.550, 0.618, 0.700, 0.786]),
    ("entry_limit_offset_atr",[0.0, 0.1, 0.2, 0.3]),
    # Volatility / regime filters
    ("atr_min_percentile",    [30.0, 35.0, 41.0, 47.0, 53.0]),
    ("atr_vol_ratio_range",   [0.7, 0.9, 1.1, 1.4, 1.6]),
    # HTF fib zone filter (now properly wired after strategy_core fix)
    ("use_fib_filter",        [False, True]),
    ("fib_zone_type",         ["full_retracement", "extended", "golden_only"]),
]

# Baseline entry params (current best, all other OAT vars held here)
BASE_ENTRY = {
    "trend_min_confluence":   6,
    "range_min_confluence":   3,
    "min_quality_factors":    4,
    "entry_fib_level":        0.636,
    "entry_limit_offset_atr": 0.0,
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
}

CSV_HEADER = ["variable", "level", "net_pnl", "max_tdd", "win_rate",
              "trades", "failed", "late_monthly_avg", "elapsed_s"]


# ── OAT helpers ──────────────────────────────────────────────────────────────

def _load_oat_done() -> set:
    """Return set of (variable, str(level)) already in the CSV."""
    done = set()
    if not OAT_CSV.exists():
        return done
    with open(OAT_CSV) as f:
        for row in csv.DictReader(f):
            done.add((row["variable"], row["level"]))
    return done


def _run_oat_task(args: tuple) -> tuple:
    """Top-level worker for ProcessPoolExecutor (must be picklable)."""
    var_name, level, tp_override = args
    t0 = time.time()
    r = dh.run_single({}, tp_override, OAT_START, OAT_END)
    elapsed = round(time.time() - t0)
    a = dh.extract_attrs(r)
    lma = round(dh.late_monthly_avg(r))
    return var_name, level, a, lma, elapsed


def phase_oat():
    """Phase 1a: parallel OAT sensitivity screen."""
    print(f"\n{'='*70}")
    print(f"  Stage 1 / Phase 1a — OAT sensitivity screen (parallel, skip-if-done)")
    print(f"  Window: {OAT_START} → {OAT_END}  |  workers: {OAT_WORKERS}")
    print(f"{'='*70}\n")
    sys.stdout.flush()

    done = _load_oat_done()
    if done:
        print(f"  Resuming — {len(done)} configs already done, skipping those.\n")

    tasks = []
    for var_name, levels in OAT_VARS:
        for level in levels:
            key = (var_name, str(level))
            if key in done:
                continue
            tp_over = dict(BASE_ENTRY)
            tp_over[var_name] = level
            if var_name == "fib_zone_type":
                tp_over["use_fib_filter"] = True
            tasks.append((var_name, level, tp_over))

    print(f"  {len(tasks)} configs to run  ({len(done)} already cached)\n")
    sys.stdout.flush()

    write_header = not OAT_CSV.exists() or OAT_CSV.stat().st_size == 0
    with open(OAT_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(CSV_HEADER)
            f.flush()

        with concurrent.futures.ProcessPoolExecutor(max_workers=OAT_WORKERS) as ex:
            futures = {ex.submit(_run_oat_task, t): t for t in tasks}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    var_name, level, a, lma, elapsed = fut.result()
                except Exception as e:
                    print(f"  ERROR in worker: {e}")
                    continue
                status = "BREACH" if a["failed"] else "OK"
                writer.writerow([var_name, level, a["net"], a["max_tdd"],
                                  a["win_rate"], a["trades"], a["failed"],
                                  lma, elapsed])
                f.flush()
                print(f"  {var_name:<26} {str(level):<22} {status:<7} "
                      f"net={a['net']:>9,}  tdd={a['max_tdd']:>5.2f}%  "
                      f"wr={a['win_rate']:>5.1f}%  trades={a['trades']:>4}  {elapsed}s")
                sys.stdout.flush()

    print(f"\n  OAT complete → {OAT_CSV}")
    _print_oat_summary()
    sys.stdout.flush()


def _print_oat_summary():
    if not OAT_CSV.exists():
        return
    from collections import defaultdict
    by_var = defaultdict(list)
    with open(OAT_CSV) as f:
        for row in csv.DictReader(f):
            by_var[row["variable"]].append(
                (row["level"], int(float(row["net_pnl"])))
            )
    print(f"\n{'─'*70}")
    print(f"  OAT Sensitivity Summary — net_pnl range per variable")
    print(f"{'─'*70}")
    ranked = []
    for var, entries in by_var.items():
        nets = [e[1] for e in entries]
        rng = max(nets) - min(nets)
        best = entries[nets.index(max(nets))][0]
        ranked.append((rng, var, best, max(nets), min(nets)))
    ranked.sort(reverse=True)
    for rng, var, best, hi, lo in ranked:
        print(f"  {var:<30}  range={rng:>10,}  best={str(best):<22}  "
              f"[{lo:,} → {hi:,}]")
    print()
    sys.stdout.flush()


# ── Optuna helpers ────────────────────────────────────────────────────────────

def _build_entry_params(trial: optuna.Trial) -> dict:
    return {
        "trend_min_confluence":   trial.suggest_int("trend_min_confluence", 4, 8),
        "range_min_confluence":   trial.suggest_int("range_min_confluence", 2, 5),
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
    entry = _build_entry_params(trial)

    # Killer starts first — cheap early-exit on breach
    for start in dh.KILLER_STARTS:
        r = dh.run_single({}, entry, start)
        a = dh.extract_attrs(r)
        trial.set_user_attr(f"net_{start[:7]}", a["net"])
        trial.set_user_attr(f"wr_{start[:7]}", a["win_rate"])
        trial.set_user_attr(f"tdd_{start[:7]}", a["max_tdd"])
        if a["failed"]:
            trial.set_user_attr("fail_start", start)
            trial.set_user_attr("breach_type", a["breach_type"])
            return -1e9 + float(a["survived_days"]) * 100

    # Passed killers — run remaining train starts
    nets = {s: trial.user_attrs[f"net_{s[:7]}"]
            for s in dh.KILLER_STARTS}
    for start in dh.TRAIN_STARTS:
        if start in dh.KILLER_STARTS:
            continue
        r = dh.run_single({}, entry, start)
        a = dh.extract_attrs(r)
        trial.set_user_attr(f"net_{start[:7]}", a["net"])
        trial.set_user_attr(f"wr_{start[:7]}", a["win_rate"])
        trial.set_user_attr(f"tdd_{start[:7]}", a["max_tdd"])
        if a["failed"]:
            trial.set_user_attr("fail_start", start)
            trial.set_user_attr("breach_type", a["breach_type"])
            return -1e9 + float(a["survived_days"]) * 100
        nets[start] = a["net"]

    mm = int(min(nets.values()))
    trial.set_user_attr("maximin", mm)
    trial.set_user_attr("entry_params", entry)
    return float(mm)


def phase_optuna(n_trials: int):
    storage = f"sqlite:///{OPTUNA_DB}"
    study = optuna.create_study(
        study_name="stage1_fib", storage=storage,
        direction="maximize", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42, n_startup_trials=15),
    )
    done = len([t for t in study.trials
                if t.state == optuna.trial.TrialState.COMPLETE])
    print(f"\n{'='*70}")
    print(f"  Stage 1 / Phase 1b — Optuna maximin  (SQLite, resumable)")
    print(f"  DB: {OPTUNA_DB}")
    print(f"  Completed so far: {done}  |  requesting: {n_trials} more")
    print(f"  Train starts: {dh.TRAIN_STARTS}")
    print(f"{'='*70}\n")
    sys.stdout.flush()

    study.optimize(_optuna_objective, n_trials=n_trials,
                   show_progress_bar=False, callbacks=[_log_trial])
    _print_optuna_summary(study)


def _log_trial(study: optuna.Study, trial: optuna.trial.FrozenTrial):
    v = trial.value or 0
    status = "OK" if v > -1e8 else f"BREACH({trial.user_attrs.get('fail_start','?')[:7]})"
    params_str = " ".join(f"{k}={v}" for k, v in trial.params.items())
    print(f"  trial {trial.number:>3}  score={v:>10,.0f}  {status}  {params_str}")
    sys.stdout.flush()


def _print_optuna_summary(study: optuna.Study):
    survivors = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE and (t.value or 0) > -1e8]
    if not survivors:
        print("  No non-breaching trials yet.\n"); return
    survivors.sort(key=lambda t: t.value, reverse=True)
    print(f"\n  Top-10 by maximin score:")
    print(f"  {'#':<4} {'score':>10}  params")
    for i, t in enumerate(survivors[:10]):
        ps = "  ".join(f"{k}={v}" for k, v in t.params.items())
        print(f"  {i+1:<4} {t.value:>10,.0f}  {ps}")
    print()
    sys.stdout.flush()


# ── Phase 1c: validate top-5 ─────────────────────────────────────────────────

def phase_validate(n_top: int = 5):
    if not OPTUNA_DB.exists():
        print("  No Optuna DB — run phase optuna first."); return
    study = optuna.load_study(study_name="stage1_fib",
                              storage=f"sqlite:///{OPTUNA_DB}")
    survivors = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE and (t.value or 0) > -1e8]
    if not survivors:
        print("  No non-breaching trials yet."); return
    survivors.sort(key=lambda t: t.value, reverse=True)

    configs = []
    for i, t in enumerate(survivors[:n_top]):
        ep = t.user_attrs.get("entry_params") or t.params
        configs.append({
            "label":       f"top{i+1}_trial{t.number}",
            "env":         {},
            "tp":          ep,
            "train_score": t.value,
        })

    print(f"\n{'='*70}")
    print(f"  Stage 1 / Phase 1c — Validating top {n_top} on TEST_STARTS + full 10yr")
    print(f"{'='*70}\n")
    validated = dh.validate_configs(configs, tag="stage1_top5")
    TOP5_JSON.write_text(json.dumps(validated, indent=2, default=str))
    print(f"\n  Saved → {TOP5_JSON}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["oat", "optuna", "validate", "all"], default="all")
    p.add_argument("--trials", type=int, default=40)
    args = p.parse_args()

    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    if args.phase in ("oat", "all"):
        phase_oat()
    if args.phase in ("optuna", "all"):
        phase_optuna(args.trials)
    if args.phase in ("validate", "all"):
        phase_validate()


if __name__ == "__main__":
    main()
