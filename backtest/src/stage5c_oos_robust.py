#!/usr/bin/env python3
"""
Stage 5c — OOS robustness: Stage 5b + 6th cold-start training window.

Differences from Stage 5b:
  - Adds a 6th training window ("2015-01-01" to "2018-12-31") as a cold-start
    period to stress-test configs against an additional out-of-sample regime.
  - Seeds loaded from top 20 non-breached rows of backtest/output/doe/stage5b.csv
    (sorted by objective descending), falling back to the original 4 Stage 5b
    seeds if the file doesn't exist or cannot be read.
  - New study "stage5c" in stage5c.db (independent of stage5b).

Usage:
    python -u backtest/src/stage5c_oos_robust.py [--trials 300] [--jobs 4]
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
WINNER_LADDER = {
    "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.6,  "tp3_r_multiple": 2.8,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.3,
    "tp1_close_pct":  0.10, "tp2_close_pct":  0.30, "tp3_close_pct": 0.20,
    "tp4_close_pct":  0.15, "tp5_close_pct":  0.25,
    "sl_after_tp2_r": 0.70, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.00,
}
BASE_RISK_PCT = 1.0

WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2019-07-01", "2022-06-30"),
    ("2015-01-01", "2018-12-31"),
]

WALL_MARGIN_TDD = float(os.getenv("WALL_MARGIN", "8.0"))
WALL_MARGIN_DDD = float(os.getenv("DDD_MARGIN",  "4.5"))
MARGIN_K        = float(os.getenv("MARGIN_K",    "20000"))

PARAM_COLS = [
    "RISK_CALM_MULT", "RISK_VOLATILE_MULT", "VOL_REGIME_DD_OFF",
    "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
    "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS",
    "CFG_TDD_WARNING_PCT", "CFG_RISK_CONSERVATIVE",
    "CFG_TDD_EMERGENCY_PCT", "CFG_RISK_ULTRASAFE", "TDD_WALL_SAFETY",
]
CSV_HEADER = (
    ["trial", "breached", "objective", "maximin", "avg_net",
     "worst_tdd", "worst_ddd", "n_survived", "fail_window"]
    + PARAM_COLS
    + [f"net_w{i}" for i in range(len(WINDOWS))]
)

# Fallback seeds: OOS-verified safe high-profit configs from stage5b
_FALLBACK_SEEDS = [
    # trial 20 — best profit, vol=0.75 calm=1.00
    {"RISK_CALM_MULT":1.00,"RISK_VOLATILE_MULT":0.75,"VOL_REGIME_DD_OFF":5.0,
     "CFG_MAX_CUM_RISK":4.5,"CFG_DAILY_HALT_PCT":2.0,"CFG_TDD_CAUTION_PCT":3.0,
     "CFG_RISK_CAUTIOUS":0.75,"CFG_TDD_WARNING_PCT":4.0,"CFG_RISK_CONSERVATIVE":0.55,
     "CFG_TDD_EMERGENCY_PCT":4.5,"CFG_RISK_ULTRASAFE":0.25,"TDD_WALL_SAFETY":5.0},
    # trial 78 — vol=0.55 calm=0.90, very clean DDD
    {"RISK_CALM_MULT":0.90,"RISK_VOLATILE_MULT":0.55,"VOL_REGIME_DD_OFF":3.5,
     "CFG_MAX_CUM_RISK":5.0,"CFG_DAILY_HALT_PCT":3.0,"CFG_TDD_CAUTION_PCT":4.5,
     "CFG_RISK_CAUTIOUS":0.75,"CFG_TDD_WARNING_PCT":5.5,"CFG_RISK_CONSERVATIVE":0.60,
     "CFG_TDD_EMERGENCY_PCT":8.5,"CFG_RISK_ULTRASAFE":0.40,"TDD_WALL_SAFETY":5.0},
    # trial 129 — vol=1.00 calm=1.30, highest profit at vol≥1
    {"RISK_CALM_MULT":1.30,"RISK_VOLATILE_MULT":1.00,"VOL_REGIME_DD_OFF":4.5,
     "CFG_MAX_CUM_RISK":4.5,"CFG_DAILY_HALT_PCT":3.25,"CFG_TDD_CAUTION_PCT":3.0,
     "CFG_RISK_CAUTIOUS":0.30,"CFG_TDD_WARNING_PCT":3.5,"CFG_RISK_CONSERVATIVE":0.25,
     "CFG_TDD_EMERGENCY_PCT":5.0,"CFG_RISK_ULTRASAFE":0.10,"TDD_WALL_SAFETY":2.5},
    # midpoint guess: vol=0.90 calm=1.10 tight daily halt
    {"RISK_CALM_MULT":1.10,"RISK_VOLATILE_MULT":0.90,"VOL_REGIME_DD_OFF":4.5,
     "CFG_MAX_CUM_RISK":4.5,"CFG_DAILY_HALT_PCT":1.75,"CFG_TDD_CAUTION_PCT":3.5,
     "CFG_RISK_CAUTIOUS":0.55,"CFG_TDD_WARNING_PCT":4.5,"CFG_RISK_CONSERVATIVE":0.35,
     "CFG_TDD_EMERGENCY_PCT":6.0,"CFG_RISK_ULTRASAFE":0.20,"TDD_WALL_SAFETY":3.0},
]


def _load_stage5b_seeds(n: int = 20) -> list:
    """Load top n non-breached seeds from stage5b.csv sorted by objective descending.

    Falls back to the original 4 hardcoded stage5b seeds if the file doesn't
    exist or cannot be read.
    """
    csv_path = DOE_DIR / "stage5b.csv"
    try:
        if not csv_path.exists():
            raise FileNotFoundError(f"{csv_path} not found")
        rows = []
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("breached", "True") == "False":
                    try:
                        obj = float(row["objective"])
                    except (KeyError, ValueError):
                        continue
                    rows.append((obj, row))
        rows.sort(key=lambda x: x[0], reverse=True)
        seeds = []
        for _, row in rows[:n]:
            seed = {}
            for col in PARAM_COLS:
                seed[col] = float(row[col])
            seeds.append(seed)
        if not seeds:
            raise ValueError("No non-breached rows found in stage5b.csv")
        return seeds
    except Exception as e:
        print(f"[stage5c] seed load warning: {e} — falling back to hardcoded seeds", flush=True)
        return _FALLBACK_SEEDS


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
            print(f"[stage5c] cleaned {n} zombie RUNNING trial(s) → FAIL", flush=True)
    except Exception as e:
        print(f"[stage5c] zombie cleanup warning: {e}", flush=True)


def _suggest(trial) -> dict:
    # Fine-grained vol/calm with step=0.01
    calm_mult  = trial.suggest_float("RISK_CALM_MULT",     0.70, 1.50, step=0.01)
    vol_mult   = trial.suggest_float("RISK_VOLATILE_MULT", 0.60, 1.30, step=0.01)
    regime_off = trial.suggest_float("VOL_REGIME_DD_OFF",  2.0,  5.0,  step=0.5)
    cum_risk   = trial.suggest_float("CFG_MAX_CUM_RISK",   2.5,  5.0,  step=0.5)
    daily_halt = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.25, 3.5,  step=0.25)
    caut_t  = trial.suggest_float("CFG_TDD_CAUTION_PCT",   3.0, 6.0, step=0.5)
    warn_t  = trial.suggest_float("CFG_TDD_WARNING_PCT",   caut_t + 0.5, 8.0, step=0.5)
    emer_t  = trial.suggest_float("CFG_TDD_EMERGENCY_PCT", warn_t + 0.5, 9.0, step=0.5)
    r_caut  = trial.suggest_float("CFG_RISK_CAUTIOUS",     0.20, 0.80, step=0.05)
    r_cons  = trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.15, min(r_caut, 0.60), step=0.05)
    r_ultra = trial.suggest_float("CFG_RISK_ULTRASAFE",    0.10, min(r_cons, 0.40), step=0.05)
    wall_safety = trial.suggest_float("TDD_WALL_SAFETY",   2.0, 5.0, step=0.5)
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

    nets, worst_tdd, worst_ddd = [], 0.0, 0.0
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
        worst_ddd = max(worst_ddd, a.get("max_ddd", 0.0) or 0.0)
        trial.set_user_attr(f"net_w{i}", a["net"])

    maximin = min(nets)
    avg_net = sum(nets) / len(nets)
    pen_tdd = MARGIN_K * max(0.0, worst_tdd - WALL_MARGIN_TDD) ** 2
    pen_ddd = MARGIN_K * max(0.0, worst_ddd - WALL_MARGIN_DDD) ** 2
    trial.set_user_attr("n_survived", len(WINDOWS))
    trial.set_user_attr("maximin",   maximin)
    trial.set_user_attr("avg_net",   round(avg_net))
    trial.set_user_attr("worst_tdd", round(worst_tdd, 2))
    trial.set_user_attr("worst_ddd", round(worst_ddd, 2))
    return maximin - pen_tdd - pen_ddd


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
            "worst_ddd":   trial.user_attrs.get("worst_ddd", ""),
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
        ddd  = trial.user_attrs.get("worst_ddd", "?")
        if not breached:
            print(f"[stage5c] trial {trial.number:3d}  OK"
                  f"  obj={v:>12,.0f}  tdd={trial.user_attrs.get('worst_tdd','?')}%"
                  f"  ddd={ddd}%  calm={calm} vol={vol}", flush=True)
        else:
            print(f"[stage5c] trial {trial.number:3d}  BREACH"
                  f"  survived={n_surv}/{len(WINDOWS)}  calm={calm} vol={vol}", flush=True)
    return callback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--jobs",   type=int, default=4)
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)
    db_path  = str(DOE_DIR / "stage5c.db")
    csv_path = DOE_DIR / "stage5c.csv"

    _cleanup_zombies(db_path)

    study = optuna.create_study(
        direction="maximize", study_name="stage5c",
        storage=f"sqlite:///{db_path}", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42, multivariate=True),
    )

    non_fail = [t for t in study.trials
                if t.state != optuna.trial.TrialState.FAIL]
    if not non_fail:
        seeds = _load_stage5b_seeds(20)
        print(f"[stage5c] Loaded {len(seeds)} seeds from stage5b.csv", flush=True)
        for s in seeds:
            study.enqueue_trial(s)
        print(f"[stage5c] Enqueued {len(seeds)} seed trials", flush=True)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE,
                              optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[stage5c] DDD+TDD penalties  step=0.01 for vol/calm  "
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
    print(f"\n[stage5c] COMPLETE — {len(survivors)} survivors", flush=True)
    if survivors:
        best = study.best_trial
        print(f"  BEST obj={best.value:,.0f}"
              f"  tdd={best.user_attrs.get('worst_tdd')}%"
              f"  ddd={best.user_attrs.get('worst_ddd')}%"
              f"  avg_net={best.user_attrs.get('avg_net'):,}"
              f"  calm={best.params.get('RISK_CALM_MULT')}"
              f"  vol={best.params.get('RISK_VOLATILE_MULT')}", flush=True)
        print(f"  env: {best.params}", flush=True)
    print("[stage5c] STAGE5C_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
