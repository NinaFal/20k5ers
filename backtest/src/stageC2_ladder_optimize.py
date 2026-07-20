#!/usr/bin/env python3
"""
Stage C2 — TP ladder Optuna, scored against the 2-step challenge objective.

Replaces the hand-made "bank_fast" ladder from earlier probing with a proper
search: TP1-3 R-multiples + close%s (TP4/5 zeroed — the challenge needs FAST
closed banking, not runners; close 100% by TP3), plus SL-trail-after levels.
Entry locked to the C1 winner (c=0.65 v=0.65 thr=1.15). Risk fixed at 3.5%
(C1's setting) — Stage C3 will retune risk jointly with regime mults.

Objective = challenge_score.score_results(...)['score'] on the 16 TRAIN starts
(same score C1 used), via full_two_step per start.

Resumable Optuna study (sqlite). Each trial = 16 full-2-step runs (~2 steps each,
short horizons) -- a trial is cheaper than a C1 grid cell sweep since only one
config is tested, but still a real grind. Multi-session.

Run (keepalive, no trailing &):
    uv run python3 backtest/src/stageC2_ladder_optimize.py [--trials 150] [--jobs 2]
"""
import argparse, csv, importlib.util, json, os
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

SKELETON = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "2.25",
            "CFG_TDD_CAUTION_PCT": "3.5", "CFG_RISK_CAUTIOUS": "0.65", "CFG_TDD_WARNING_PCT": "4.5",
            "CFG_RISK_CONSERVATIVE": "0.6", "CFG_TDD_EMERGENCY_PCT": "8.0", "CFG_RISK_ULTRASAFE": "0.4",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3"}
RISK = 3.5
# C1 winner entry, locked.
ENTRY = dict(scr.PINNED_ENTRY)
ENTRY.update({"entry_fib_level": 0.65, "entry_fib_level_volatile": 0.65,
              "fib_vol_ratio_threshold": 1.15})

PARAM_COLS = ["tp1_r", "tp2_r", "tp3_r", "c1", "c2", "sl_after_tp2_r", "sl_after_tp3_r"]
CSV_HEADER = ["trial", "score", "p20", "p40", "breach_rate", "median_total"] + PARAM_COLS


def _suggest(trial):
    tp1 = trial.suggest_float("tp1_r", 0.3, 0.8, step=0.05)
    tp2 = trial.suggest_float("tp2_r", tp1 + 0.2, 1.5, step=0.05)
    tp3 = trial.suggest_float("tp3_r", tp2 + 0.2, 2.5, step=0.1)
    c1 = trial.suggest_float("c1", 0.30, 0.70, step=0.05)     # tp1 close%
    c2 = trial.suggest_float("c2", 0.20, 0.60, step=0.05)     # tp2 close% (tp3 = remainder)
    sl2 = trial.suggest_float("sl_after_tp2_r", 0.2, tp1, step=0.05)
    sl3 = trial.suggest_float("sl_after_tp3_r", tp1, tp2, step=0.1)
    c3 = max(0.0, 1.0 - c1 - c2)
    tp = {
        "tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
        "tp4_r_multiple": tp3 + 1.0, "tp5_r_multiple": tp3 + 2.0,   # unreachable (0% close)
        "tp1_close_pct": c1, "tp2_close_pct": c2, "tp3_close_pct": c3,
        "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
        "sl_after_tp2_r": sl2, "sl_after_tp3_r": sl3, "sl_after_tp4_r": tp2,
        "risk_per_trade_pct": RISK,
    }
    return tp


def objective(trial):
    tp_lever = _suggest(trial)
    tp = {**ENTRY, **tp_lever}
    rows = []
    for start in cs.TRAIN_STARTS:
        r = cs.full_two_step(SKELETON, tp, start)
        r.pop("detail", None)
        rows.append(r)
    sc = cs.score_results(rows)
    trial.set_user_attr("p20", sc["p20"]); trial.set_user_attr("p40", sc["p40"])
    trial.set_user_attr("breach_rate", sc["breach_rate"])
    trial.set_user_attr("median_total", sc["median_total"])
    return sc["score"]


def make_cb(csv_path):
    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               "p20": trial.user_attrs.get("p20"), "p40": trial.user_attrs.get("p40"),
               "breach_rate": trial.user_attrs.get("breach_rate"),
               "median_total": trial.user_attrs.get("median_total"),
               **{k: trial.params.get(k, "") for k in PARAM_COLS}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if new: w.writeheader()
            w.writerow(row)
        print(f"[C2] trial {trial.number:3d}  score={trial.value:7.2f}"
              f"  p20={trial.user_attrs.get('p20')}  p40={trial.user_attrs.get('p40')}"
              f"  breach={trial.user_attrs.get('breach_rate')}"
              f"  medTot={trial.user_attrs.get('median_total')}"
              f"  tp={trial.params.get('tp1_r')}/{trial.params.get('tp2_r')}/{trial.params.get('tp3_r')}"
              f"  c={trial.params.get('c1')}/{trial.params.get('c2')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageC2.db"); csv_path = DOE_DIR / "stageC2.csv"

    study = optuna.create_study(direction="maximize", study_name="stageC2",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    # Seed with the hand-made bank_fast ladder as a floor.
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        study.enqueue_trial({"tp1_r": 0.5, "tp2_r": 1.0, "tp3_r": 1.5,
                             "c1": 0.45, "c2": 0.35,
                             "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[C2] ladder optimize — {done} done, {remaining} remaining, "
          f"{len(cs.TRAIN_STARTS)} starts/trial, jobs={args.jobs}", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs,
                       callbacks=[make_cb(csv_path)], catch=(Exception,))

    best = study.best_trial
    print(f"\n[C2] BEST score={best.value:.2f} p20={best.user_attrs.get('p20')}"
          f" p40={best.user_attrs.get('p40')} breach={best.user_attrs.get('breach_rate')}"
          f" medTot={best.user_attrs.get('median_total')}", flush=True)
    print(f"  params: {best.params}", flush=True)
    print("[stageC2_ladder_optimize] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
