#!/usr/bin/env python3
"""
Stage 3 — Take-profit ladder optimisation (Optuna).

Locked from Stage 1+2:
  Entry A signal (fib 0.55 calm / 0.80 volatile, ratio_thr 1.05)
  BASE_RISK_PCT = 1.1% (Stage 1 anchor)
  Regime-coherent risk: calm=1.15× / volatile=0.55× (Stage 2 winner, trial 25)
  All 12 risk/sizing / circuit-breaker params (Stage 2 trial 25)

Optimised here (13 dims):
  tp1-tp5 R-multiples (ordered: tp1 < tp2 < tp3 < tp4 < tp5)
  tp1-tp4 close_pct   (tp5 = 1 - sum; constrained >= 0.08)
  sl_after_tp2_r, sl_after_tp3_r, sl_after_tp4_r (monotonically increasing trail)

OBJECTIVE (priority order):
  1. Never breach → any window breach = -1e9 + n_survived×1e6
  2. Maximise maximin net (worst-window net PnL across 5 regime windows)
  3. Penalise TDD hugging (worst_tdd > 8% → quadratic penalty)

CRASH-PROOF: CSV append-per-trial (flush after each), resumable SQLite study,
  zombie RUNNING cleanup at startup. Wrap with watchdog_stage3.sh.

Usage:
    python -u backtest/src/stage3_tp_ladder.py --trials 100
    python -u backtest/src/stage3_tp_ladder.py --trials 100 --jobs 4
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

# ── Stage 1 anchor ────────────────────────────────────────────────────────────
BASE_RISK_PCT = 1.1

# ── Stage 2 winner — locked env overrides (Entry A, trial 25) ────────────────
# Applied on top of doe_harness.BASE_ENV in every run_single call.
STAGE2_WINNER_ENV = {
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

# ── Stage 1 entry signal — locked ────────────────────────────────────────────
PINNED_ENTRY = {
    "trend_min_confluence":   6,
    "range_min_confluence":   3,
    "min_quality_factors":    3,
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
    "entry_limit_offset_atr": 0.0,
}

ENTRY_A = {
    "entry_fib_level":         0.55,
    "entry_fib_level_volatile": 0.80,
    "fib_vol_ratio_threshold": 1.05,
    "use_trend_quality_gate":  False,
    "adx_min_entry":           0.0,
}

# Fixed portion of OPT_PARAMS (entry signal + risk anchor).
# TP ladder params are merged on top by the objective.
FIXED_TP = {**PINNED_ENTRY, **ENTRY_A, "risk_per_trade_pct": BASE_RISK_PCT}

# ── Evaluation windows (worst-first for early breach veto) ───────────────────
WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2019-07-01", "2022-06-30"),
]

WALL_MARGIN = float(os.getenv("WALL_MARGIN", "8.0"))
MARGIN_K    = float(os.getenv("MARGIN_K", "20000"))

# ── CSV schema ────────────────────────────────────────────────────────────────
PARAM_COLS = [
    "tp1_r_multiple", "tp2_r_multiple", "tp3_r_multiple",
    "tp4_r_multiple", "tp5_r_multiple",
    "tp1_close_pct",  "tp2_close_pct",  "tp3_close_pct",
    "tp4_close_pct",  "tp5_close_pct",
    "sl_after_tp2_r", "sl_after_tp3_r", "sl_after_tp4_r",
]
CSV_HEADER = (
    ["trial", "breached", "objective", "maximin", "avg_net", "worst_tdd",
     "n_survived", "fail_window"]
    + PARAM_COLS
    + [f"net_w{i}" for i in range(len(WINDOWS))]
)


# ── Seeds — three TP ladder archetypes as starting points ────────────────────
# 1. doe_harness BASE_TP  — current best from Stage 2 tuning run
# 2. Current live params  — tight early-exit ladder
# 3. Old aggressive winner — rides long to TP5
SEEDS = [
    {  # doe_harness BASE_TP (Stage 2 base)
        "tp1_r_multiple": 0.9,  "tp2_r_multiple": 1.7,  "tp3_r_multiple": 2.4,
        "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.7,
        "tp1_close_pct":  0.10, "tp2_close_pct":  0.35, "tp3_close_pct": 0.15,
        "tp4_close_pct":  0.10,
        "sl_after_tp2_r": 0.7,  "sl_after_tp3_r": 1.6,  "sl_after_tp4_r": 2.0,
    },
    {  # current live params (current_params.json)
        "tp1_r_multiple": 0.6,  "tp2_r_multiple": 0.9,  "tp3_r_multiple": 1.3,
        "tp4_r_multiple": 2.0,  "tp5_r_multiple": 3.5,
        "tp1_close_pct":  0.25, "tp2_close_pct":  0.30, "tp3_close_pct": 0.15,
        "tp4_close_pct":  0.20,
        "sl_after_tp2_r": 0.50, "sl_after_tp3_r": 0.90, "sl_after_tp4_r": 0.90,
    },
    {  # old aggressive winner
        "tp1_r_multiple": 0.9,  "tp2_r_multiple": 1.8,  "tp3_r_multiple": 2.5,
        "tp4_r_multiple": 3.2,  "tp5_r_multiple": 5.0,
        "tp1_close_pct":  0.15, "tp2_close_pct":  0.15, "tp3_close_pct": 0.10,
        "tp4_close_pct":  0.10,
        "sl_after_tp2_r": 0.50, "sl_after_tp3_r": 0.55, "sl_after_tp4_r": 0.70,
    },
]


def _cleanup_zombie_trials(db_path: str):
    if not Path(db_path).exists():
        return
    try:
        with sqlite3.connect(db_path) as conn:
            n = conn.execute(
                "UPDATE trials SET state='FAIL' WHERE state='RUNNING'"
            ).rowcount
            conn.commit()
        if n:
            print(f"[stage3] cleaned {n} zombie RUNNING trial(s) → FAIL", flush=True)
    except Exception as e:
        print(f"[stage3] zombie cleanup warning: {e}", flush=True)


def _suggest(trial) -> dict:
    """Suggest TP ladder with ordering + close-pct sum constraints."""
    tp1 = trial.suggest_float("tp1_r_multiple", 0.4, 1.0,       step=0.1)
    tp2 = trial.suggest_float("tp2_r_multiple", tp1 + 0.2, 1.8, step=0.1)
    tp3 = trial.suggest_float("tp3_r_multiple", tp2 + 0.2, 2.8, step=0.1)
    tp4 = trial.suggest_float("tp4_r_multiple", tp3 + 0.3, 4.0, step=0.1)
    tp5 = trial.suggest_float("tp5_r_multiple", tp4 + 0.3, 6.0, step=0.1)

    c1 = trial.suggest_float("tp1_close_pct", 0.10, 0.45, step=0.05)
    c2 = trial.suggest_float("tp2_close_pct", 0.10, 0.45, step=0.05)
    c3 = trial.suggest_float("tp3_close_pct", 0.05, 0.30, step=0.05)
    c4 = trial.suggest_float("tp4_close_pct", 0.05, 0.30, step=0.05)
    if c1 + c2 + c3 + c4 > 0.92:   # leave ≥8% to ride to TP5
        raise optuna.TrialPruned()
    c5 = round(1.0 - c1 - c2 - c3 - c4, 4)

    # Trailing SL — monotonically increasing, stays below the TP it protects
    s2 = trial.suggest_float("sl_after_tp2_r", 0.20, min(tp1, 1.0),  step=0.05)
    s3 = trial.suggest_float("sl_after_tp3_r", s2,   min(tp2, 1.60), step=0.05)
    s4 = trial.suggest_float("sl_after_tp4_r", s3,   min(tp3, 2.20), step=0.05)

    return {
        "tp1_r_multiple": tp1, "tp2_r_multiple": tp2,
        "tp3_r_multiple": tp3, "tp4_r_multiple": tp4, "tp5_r_multiple": tp5,
        "tp1_close_pct": c1,  "tp2_close_pct": c2,
        "tp3_close_pct": c3,  "tp4_close_pct": c4,  "tp5_close_pct": c5,
        "sl_after_tp2_r": s2, "sl_after_tp3_r": s3, "sl_after_tp4_r": s4,
    }


def objective(trial):
    tp_ladder = _suggest(trial)
    tp_over   = {**FIXED_TP, **tp_ladder}

    # Store tp5_close_pct as user_attr (computed, not a trial.suggest param)
    trial.set_user_attr("tp5_close_pct", tp_ladder["tp5_close_pct"])

    nets, worst_tdd = [], 0.0
    for i, (start, end) in enumerate(WINDOWS):
        r = dh.run_single(STAGE2_WINNER_ENV, tp_over, start, end)
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
    trial.set_user_attr("maximin",  maximin)
    trial.set_user_attr("avg_net",  round(avg_net))
    trial.set_user_attr("worst_tdd", round(worst_tdd, 2))
    return maximin - pen


def make_csv_callback(csv_path: Path):
    def callback(study, trial):
        if trial.state not in (optuna.trial.TrialState.COMPLETE,
                               optuna.trial.TrialState.PRUNED):
            return
        v        = trial.value or 0.0
        breached = v < -1e8
        n_surv   = trial.user_attrs.get("n_survived",
                   len(WINDOWS) if not breached else 0)
        # tp5_close_pct: user_attr (set in objective) or computed fallback
        tp5_pct = trial.user_attrs.get("tp5_close_pct") or round(
            1.0 - sum(trial.params.get(f"tp{i}_close_pct", 0) for i in range(1, 5)), 4)
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
            **{k: trial.params.get(k, trial.user_attrs.get(k, ""))
               for k in PARAM_COLS},
            **{f"net_w{i}": trial.user_attrs.get(f"net_w{i}", "")
               for i in range(len(WINDOWS))},
        }
        # tp5_close_pct isn't in trial.params — inject from user_attr
        row["tp5_close_pct"] = tp5_pct

        write_hdr = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if write_hdr:
                writer.writeheader()
            writer.writerow(row)
            f.flush()

        tp1 = trial.params.get("tp1_r_multiple", "?")
        tp3 = trial.params.get("tp3_r_multiple", "?")
        tp5 = trial.params.get("tp5_r_multiple", "?")
        if not breached:
            print(f"[stage3] trial {trial.number:3d}  OK"
                  f"  obj={v:>12,.0f}"
                  f"  maximin={trial.user_attrs.get('maximin','?'):>10,.0f}"
                  f"  avg_net={trial.user_attrs.get('avg_net','?'):>8,}"
                  f"  tdd={trial.user_attrs.get('worst_tdd','?')}%"
                  f"  tp={tp1}/{tp3}/{tp5}R", flush=True)
        else:
            print(f"[stage3] trial {trial.number:3d}  BREACH"
                  f"  survived={n_surv}/5"
                  f"  tp={tp1}/{tp3}/{tp5}R", flush=True)

    return callback


def _replay_csv(study, csv_path: Path):
    """Write already-complete DB trials missing from the CSV (resume-safe)."""
    existing = set()
    if csv_path.exists() and csv_path.stat().st_size > 0:
        with open(csv_path, newline="") as f:
            existing = {int(r["trial"]) for r in csv.DictReader(f)
                        if r.get("trial", "").lstrip("-").isdigit()}
    replayed = 0
    cb = make_csv_callback(csv_path)
    for t in study.trials:
        if (t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED)
                and t.number not in existing):
            cb(study, t)
            replayed += 1
    if replayed:
        print(f"[stage3] replayed {replayed} existing trials to CSV", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Stage 3 TP-ladder Optuna optimiser.")
    ap.add_argument("--trials", type=int, default=100)
    ap.add_argument("--jobs",   type=int, default=1)
    args = ap.parse_args()

    csv_path = DOE_DIR / "stage3.csv"
    db_path  = str(DOE_DIR / "stage3.db")
    storage  = f"sqlite:///{db_path}"

    _cleanup_zombie_trials(db_path)

    study = optuna.create_study(
        direction="maximize", study_name="stage3_tp",
        storage=storage, load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    # Enqueue seeds only if no non-FAIL trials exist yet
    non_fail = [t for t in study.trials
                if t.state not in (optuna.trial.TrialState.FAIL,)]
    if not non_fail:
        for s in SEEDS:
            # tp5_close_pct is computed — enqueue only the 12 suggest params
            seed_params = {k: v for k, v in s.items() if k != "tp5_close_pct"}
            study.enqueue_trial(seed_params)
        print(f"[stage3] enqueued {len(SEEDS)} seed trials", flush=True)

    _replay_csv(study, csv_path)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE,
                              optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[stage3] STAGE2_WINNER: calm=1.15× vol=0.55×  BASE_RISK={BASE_RISK_PCT}%"
          f"  WALL_MARGIN={WALL_MARGIN}%", flush=True)
    print(f"[stage3] {done} done, {remaining} remaining"
          f" (target {args.trials}), jobs={args.jobs}", flush=True)
    sys.stdout.flush()

    if remaining > 0:
        study.optimize(
            objective,
            n_trials=remaining,
            n_jobs=args.jobs,
            callbacks=[make_csv_callback(csv_path)],
        )

    done_final = sum(1 for t in study.trials
                     if t.state in (optuna.trial.TrialState.COMPLETE,
                                    optuna.trial.TrialState.PRUNED))
    survivors = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE and t.value is not None
                 and t.value > -1e8]
    print(f"\n[stage3] STAGE3 COMPLETE — {done_final} done,"
          f" {len(survivors)} surviving", flush=True)
    if survivors:
        best = study.best_trial
        p = best.params
        print(f"  BEST obj={best.value:,.0f}"
              f"  maximin={best.user_attrs.get('maximin'):,.0f}"
              f"  avg_net={best.user_attrs.get('avg_net'):,}"
              f"  worst_tdd={best.user_attrs.get('worst_tdd')}%", flush=True)
        tp5 = best.user_attrs.get("tp5_close_pct") or round(
            1.0 - sum(p.get(f"tp{i}_close_pct", 0) for i in range(1, 5)), 4)
        print(f"  TP ladder: {p['tp1_r_multiple']:.1f}/{p['tp2_r_multiple']:.1f}/"
              f"{p['tp3_r_multiple']:.1f}/{p['tp4_r_multiple']:.1f}/"
              f"{p['tp5_r_multiple']:.1f}R", flush=True)
        print(f"  close%: {p['tp1_close_pct']:.2f}/{p['tp2_close_pct']:.2f}/"
              f"{p['tp3_close_pct']:.2f}/{p['tp4_close_pct']:.2f}/{tp5:.2f}", flush=True)
        print(f"  sl_trail: tp2@{p['sl_after_tp2_r']:.2f}R"
              f"  tp3@{p['sl_after_tp3_r']:.2f}R"
              f"  tp4@{p['sl_after_tp4_r']:.2f}R", flush=True)
    print(f"[stage3] STAGE3_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
