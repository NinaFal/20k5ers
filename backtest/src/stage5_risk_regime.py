#!/usr/bin/env python3
"""
Stage 5 — Risk regime re-tune with locked Stage 4 TP/SL ladder (Optuna).

Stage 2 found the risk regime (halt %, caution/warning/emergency TDD thresholds)
using the old Stage 3 ladder (trial 68, risk=1.1%).  The Stage 4 Pareto optimizer
found a better TP/SL ladder (trial 170, risk=1.0%) — different TP targets and
close fractions shift the P&L distribution, so the optimal risk regime changes.

This script re-runs the same risk regime search space as Stage 2 but with:
  - BASE_RISK = 1.0%  (locked Stage 4 value)
  - WINNER_LADDER = trial 170 TP/SL params (locked)

Seeds include the current Stage 2 winner (WINNER_ENV) so Optuna explores
from a known-good starting point.

Usage:
    python -u backtest/src/stage5_risk_regime.py [--trials 150] [--jobs 4]
"""
import argparse
import csv
import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE  = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh    = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR = dh.DOE_DIR

# ── Locked Stage 1 entry ──────────────────────────────────────────────────────
PINNED_ENTRY = {
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

# ── Locked Stage 4 TP/SL ladder (Pareto trial 170) ───────────────────────────
WINNER_LADDER = {
    "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.6,  "tp3_r_multiple": 2.8,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.3,
    "tp1_close_pct":  0.10, "tp2_close_pct":  0.30, "tp3_close_pct": 0.20,
    "tp4_close_pct":  0.15, "tp5_close_pct":  0.25,
    "sl_after_tp2_r": 0.70, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.00,
}

BASE_RISK_PCT = 1.0  # locked Stage 4 value

# Windows worst-first so breachy trials veto early.
WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2019-07-01", "2022-06-30"),
]

WALL_MARGIN = float(os.getenv("WALL_MARGIN", "8.0"))
MARGIN_K    = float(os.getenv("MARGIN_K", "20000"))

PARAM_COLS = [
    "RISK_CALM_MULT", "RISK_VOLATILE_MULT", "VOL_REGIME_DD_OFF",
    "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
    "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS",
    "CFG_TDD_WARNING_PCT", "CFG_RISK_CONSERVATIVE",
    "CFG_TDD_EMERGENCY_PCT", "CFG_RISK_ULTRASAFE", "TDD_WALL_SAFETY",
]
CSV_HEADER = (
    ["trial", "breached", "objective", "maximin", "avg_net", "worst_tdd",
     "n_survived", "fail_window"]
    + PARAM_COLS
    + [f"net_w{i}" for i in range(len(WINDOWS))]
)

# Seed: Stage 2 winner (current WINNER_ENV) + bracket variants
_BASE_SEED = {
    "RISK_CALM_MULT": 1.15, "RISK_VOLATILE_MULT": 0.55,
    "VOL_REGIME_DD_OFF": 2.5, "CFG_MAX_CUM_RISK": 4.0,
    "CFG_DAILY_HALT_PCT": 2.0,
    "CFG_TDD_CAUTION_PCT": 4.0,  "CFG_RISK_CAUTIOUS": 0.30,
    "CFG_TDD_WARNING_PCT": 5.5,  "CFG_RISK_CONSERVATIVE": 0.25,
    "CFG_TDD_EMERGENCY_PCT": 8.0, "CFG_RISK_ULTRASAFE": 0.15,
    "TDD_WALL_SAFETY": 5.0,
}
SEEDS = [
    _BASE_SEED,                                                              # Stage 2 winner
    {**_BASE_SEED, "RISK_CALM_MULT": 1.30, "RISK_VOLATILE_MULT": 0.45},    # more calm bias
    {**_BASE_SEED, "RISK_CALM_MULT": 1.00, "RISK_VOLATILE_MULT": 0.65},    # less asymmetry
    {**_BASE_SEED, "CFG_DAILY_HALT_PCT": 1.5, "TDD_WALL_SAFETY": 4.0},     # tighter circuit
]


def _cleanup_zombies(db_path: str):
    if not Path(db_path).exists():
        return
    try:
        with sqlite3.connect(db_path) as conn:
            n = conn.execute(
                "UPDATE trials SET state='FAIL' WHERE state='RUNNING'"
            ).rowcount
            conn.commit()
        if n:
            print(f"[stage5] cleaned {n} zombie RUNNING trial(s) → FAIL", flush=True)
    except Exception as e:
        print(f"[stage5] zombie cleanup warning: {e}", flush=True)


def _suggest(trial) -> dict:
    calm_mult  = trial.suggest_float("RISK_CALM_MULT",     0.50, 1.50, step=0.05)
    vol_mult   = trial.suggest_float("RISK_VOLATILE_MULT", 0.40, 1.80, step=0.05)
    regime_off = trial.suggest_float("VOL_REGIME_DD_OFF",  2.0,  5.0,  step=0.5)
    cum_risk   = trial.suggest_float("CFG_MAX_CUM_RISK",   2.5,  5.0,  step=0.5)
    daily_halt = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.5,  3.5,  step=0.25)
    caut_t  = trial.suggest_float("CFG_TDD_CAUTION_PCT",   3.0, 6.0, step=0.5)
    warn_t  = trial.suggest_float("CFG_TDD_WARNING_PCT",   caut_t + 0.5, 8.0, step=0.5)
    emer_t  = trial.suggest_float("CFG_TDD_EMERGENCY_PCT", warn_t + 0.5, 9.0, step=0.5)
    r_caut  = trial.suggest_float("CFG_RISK_CAUTIOUS",     0.20, 0.80, step=0.05)
    r_cons  = trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.15, min(r_caut, 0.60), step=0.05)
    r_ultra = trial.suggest_float("CFG_RISK_ULTRASAFE",    0.10, min(r_cons, 0.40), step=0.05)
    wall_safety = trial.suggest_float("TDD_WALL_SAFETY",   2.0,  5.0, step=0.5)
    return {
        "RISK_REGIME_ENABLE":    "1",
        "VOL_SIZE_ENABLE":       "0",
        "RISK_CALM_MULT":        f"{calm_mult}",
        "RISK_VOLATILE_MULT":    f"{vol_mult}",
        "VOL_REGIME_DD_OFF":     f"{regime_off}",
        "VOL_REGIME_DD_MULT":    "1.0",
        "CFG_MAX_CUM_RISK":      f"{cum_risk}",
        "CFG_DAILY_HALT_PCT":    f"{daily_halt}",
        "CFG_TDD_CAUTION_PCT":   f"{caut_t}",
        "CFG_RISK_CAUTIOUS":     f"{r_caut}",
        "CFG_TDD_WARNING_PCT":   f"{warn_t}",
        "CFG_RISK_CONSERVATIVE": f"{r_cons}",
        "CFG_TDD_EMERGENCY_PCT": f"{emer_t}",
        "CFG_RISK_ULTRASAFE":    f"{r_ultra}",
        "TDD_WALL_SAFETY":       f"{wall_safety}",
    }


def objective(trial):
    env_over = _suggest(trial)
    tp_over  = {**PINNED_ENTRY, **WINNER_LADDER, "risk_per_trade_pct": BASE_RISK_PCT}

    nets, worst_tdd = [], 0.0
    for i, (start, end) in enumerate(WINDOWS):
        r = dh.run_single(env_over, tp_over, start, end)
        if r is None:
            trial.set_user_attr("infra_fail_window", i)
            trial.set_user_attr("n_survived", len(nets))
            return -3e9
        a = dh.extract_attrs(r)
        if a["failed"]:
            trial.set_user_attr("fail_window", i)
            trial.set_user_attr("n_survived", len(nets))
            return -1e9 + len(nets) * 1e6
        nets.append(a["net"])
        worst_tdd = max(worst_tdd, a.get("max_tdd", 0.0) or 0.0)
        trial.set_user_attr(f"net_w{i}", a["net"])

    maximin = min(nets)
    avg_net = sum(nets) / len(nets)
    pen = MARGIN_K * max(0.0, worst_tdd - WALL_MARGIN) ** 2
    trial.set_user_attr("n_survived", len(WINDOWS))
    trial.set_user_attr("maximin", maximin)
    trial.set_user_attr("avg_net", round(avg_net))
    trial.set_user_attr("worst_tdd", round(worst_tdd, 2))
    return maximin - pen


def make_csv_callback(csv_path: Path):
    def callback(study, trial):
        if trial.state not in (optuna.trial.TrialState.COMPLETE,
                               optuna.trial.TrialState.PRUNED):
            return
        v = trial.value or 0.0
        breached = v < -1e8
        n_surv = trial.user_attrs.get("n_survived", len(WINDOWS) if not breached else 0)
        row = {
            "trial":       trial.number,
            "breached":    breached,
            "objective":   round(v, 2),
            "maximin":     trial.user_attrs.get("maximin", ""),
            "avg_net":     trial.user_attrs.get("avg_net", ""),
            "worst_tdd":   trial.user_attrs.get("worst_tdd", ""),
            "n_survived":  n_surv,
            "fail_window": trial.user_attrs.get("fail_window",
                           trial.user_attrs.get("infra_fail_window", "")),
            **{k: trial.params.get(k, "") for k in PARAM_COLS},
            **{f"net_w{i}": trial.user_attrs.get(f"net_w{i}", "")
               for i in range(len(WINDOWS))},
        }
        write_hdr = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if write_hdr:
                writer.writeheader()
            writer.writerow(row)
            f.flush()
        calm = trial.params.get("RISK_CALM_MULT", "?")
        vol  = trial.params.get("RISK_VOLATILE_MULT", "?")
        if not breached:
            print(f"[stage5] trial {trial.number:3d}  OK"
                  f"  obj={v:>12,.0f}  maximin={trial.user_attrs.get('maximin','?'):>10,.0f}"
                  f"  tdd={trial.user_attrs.get('worst_tdd','?')}%"
                  f"  calm={calm} vol={vol}", flush=True)
        else:
            print(f"[stage5] trial {trial.number:3d}  BREACH"
                  f"  survived={n_surv}/5  calm={calm} vol={vol}", flush=True)
    return callback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--jobs",   type=int, default=4)
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)
    db_path  = str(DOE_DIR / "stage5.db")
    csv_path = DOE_DIR / "stage5.csv"

    _cleanup_zombies(db_path)

    study = optuna.create_study(
        direction="maximize", study_name="stage5",
        storage=f"sqlite:///{db_path}", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42, multivariate=True),
    )

    non_fail = [t for t in study.trials
                if t.state != optuna.trial.TrialState.FAIL]
    if not non_fail:
        for s in SEEDS:
            study.enqueue_trial(s)
        print(f"[stage5] Enqueued {len(SEEDS)} seed trials", flush=True)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE,
                              optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[stage5] BASE_RISK={BASE_RISK_PCT}%  ladder=trial170  "
          f"{done} done, {remaining} remaining (target {args.trials}), "
          f"jobs={args.jobs}", flush=True)

    if remaining > 0:
        study.optimize(
            objective,
            n_trials=remaining,
            n_jobs=args.jobs,
            callbacks=[make_csv_callback(csv_path)],
            catch=(Exception,),
        )

    survivors = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE and t.value > -1e8]
    print(f"\n[stage5] COMPLETE — {len(survivors)} survivors", flush=True)
    if survivors:
        best = study.best_trial
        print(f"  BEST obj={best.value:,.0f}"
              f"  maximin={best.user_attrs.get('maximin'):,.0f}"
              f"  avg_net={best.user_attrs.get('avg_net'):,}"
              f"  worst_tdd={best.user_attrs.get('worst_tdd')}%", flush=True)
        print(f"  env: {best.params}", flush=True)
    print("[stage5] STAGE5_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
