#!/usr/bin/env python3
"""
Stage C2 (3%-wall R&D) — TP ladder + risk + position-cap Optuna.

Phase 3 (3% Summer Edition wall) has NEVER had its own ladder search — it
inherited the Phase-2 fast-banking ladder (bank_fast / trial4), which was
tuned under the WRONG (5%) wall assumption and breaches 87.5% of TRAIN starts
at 3% (STAGEC2_TRIAL4_BACKUP.md). This is the first proper ladder search done
under the CORRECT constraints: 3% wall, MAX_TOTAL_POSITIONS lever, entry
locked to the just-completed C1-wall3 winner.

Entry LOCKED: c=0.45 v=0.80 thr=1.05 (tied-best of the C1 relaxed-target
follow-up, score 5.7, 0% breach, median completion 52 days when it finishes).

Searches jointly (since the ladder shape and how much risk/exposure it can
safely carry are coupled):
  tp1-3 R-multiples + close%s (100% closed by TP3, no runners -- challenge
  phase needs FAST closed banking), sl-trail-after levels, risk_per_trade_pct,
  CORR_GROUP_CAP, MAX_TOTAL_POSITIONS.
Regime mults (RISK_CALM_MULT/RISK_VOLATILE_MULT) held at the inherited Phase
1/2 values for now -- a separate re-tune (C3-wall3) if this doesn't help.

Objective = challenge_score.score_results on the 16 TRAIN starts (score
formula now: 2*p20 + 3*p30 + 1*p60 - 10*breach - median/100 -- p30, the
"pass within a month" target, is primary).

Resumable sqlite study. Concurrency INSIDE objective() (over 16 starts, NOT
across trials -- Optuna's sqlite storage races under n_jobs>1, see the C2/C3
postmortems in Phase 2's history).

Run (keepalive via Bash run_in_background, NO trailing &):
    uv run python3 backtest/src/stageC2_wall3_ladder_optimize.py [--trials 150]
"""
import argparse, concurrent.futures, csv, importlib.util, os
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

# C1-wall3 winner entry, locked.
ENTRY = dict(scr.PINNED_ENTRY)
ENTRY.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
              "fib_vol_ratio_threshold": 1.05})

# Regime mults held fixed (inherited from Phase 1/2 sizing work) -- only the
# ladder + risk + caps are searched here.
FIXED_REGIME = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
                "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
                "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "2.5", "CFG_DAILY_HALT_PCT": "2.0",
                "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
                "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
                "TDD_WALL_SAFETY": "4.0"}

PARAM_COLS = ["tp1_r", "tp2_r", "tp3_r", "c1", "c2", "sl_after_tp2_r", "sl_after_tp3_r",
              "risk_per_trade_pct", "CORR_GROUP_CAP", "MAX_TOTAL_POSITIONS"]
CSV_HEADER = ["trial", "score", "p20", "p30", "p40", "p60", "breach_rate", "median_total"] + PARAM_COLS


def _suggest(trial):
    tp1 = trial.suggest_float("tp1_r", 0.2, 0.7, step=0.05)
    tp2 = trial.suggest_float("tp2_r", tp1 + 0.15, 1.3, step=0.05)
    tp3 = trial.suggest_float("tp3_r", tp2 + 0.15, 2.2, step=0.1)
    c1 = trial.suggest_float("c1", 0.30, 0.70, step=0.05)
    c2 = trial.suggest_float("c2", 0.20, 0.60, step=0.05)
    sl2 = trial.suggest_float("sl_after_tp2_r", 0.1, tp1, step=0.05)
    sl3 = trial.suggest_float("sl_after_tp3_r", tp1, tp2, step=0.1)
    risk = trial.suggest_float("risk_per_trade_pct", 0.4, 2.0, step=0.1)
    cap = trial.suggest_categorical("CORR_GROUP_CAP", [2, 3, 4])
    maxpos = trial.suggest_categorical("MAX_TOTAL_POSITIONS", [5, 8, 10, 12, 15, 20])
    c3 = max(0.0, 1.0 - c1 - c2)
    tp = {
        **ENTRY,
        "tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
        "tp4_r_multiple": tp3 + 1.0, "tp5_r_multiple": tp3 + 2.0,  # unreachable, 0% close
        "tp1_close_pct": c1, "tp2_close_pct": c2, "tp3_close_pct": c3,
        "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
        "sl_after_tp2_r": sl2, "sl_after_tp3_r": sl3, "sl_after_tp4_r": tp2,
        "risk_per_trade_pct": risk,
    }
    env = dict(FIXED_REGIME)
    env["CORR_GROUP_CAP"] = f"{cap}"
    env["MAX_TOTAL_POSITIONS"] = f"{maxpos}"
    return env, tp


def objective(trial):
    env, tp = _suggest(trial)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(cs.full_two_step, env, tp, start) for start in cs.TRAIN_STARTS]
        for fut in futs:
            r = fut.result()
            r.pop("detail", None)
            rows.append(r)
    sc = cs.score_results(rows)
    for k in ("p20", "p30", "p40", "p60", "breach_rate", "median_total"):
        trial.set_user_attr(k, sc[k])
    return sc["score"]


def make_cb(csv_path):
    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               **{k: trial.user_attrs.get(k) for k in ("p20", "p30", "p40", "p60", "breach_rate", "median_total")},
               **{k: trial.params.get(k, "") for k in PARAM_COLS}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if new: w.writeheader()
            w.writerow(row)
        print(f"[C2w3] trial {trial.number:3d}  score={trial.value:7.2f}"
              f"  p20={trial.user_attrs.get('p20')} p30={trial.user_attrs.get('p30')}"
              f"  p60={trial.user_attrs.get('p60')}"
              f"  breach={trial.user_attrs.get('breach_rate')}"
              f"  medTot={trial.user_attrs.get('median_total')}"
              f"  tp={trial.params.get('tp1_r')}/{trial.params.get('tp2_r')}/{trial.params.get('tp3_r')}"
              f"  risk={trial.params.get('risk_per_trade_pct')}"
              f"  cap={trial.params.get('CORR_GROUP_CAP')}"
              f"  maxpos={trial.params.get('MAX_TOTAL_POSITIONS')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--jobs", type=int, default=1)  # keep 1 -- sqlite race under n_jobs>1
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageC2_wall3.db"); csv_path = DOE_DIR / "stageC2_wall3.csv"

    study = optuna.create_study(direction="maximize", study_name="stageC2_wall3",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        # Seed with the inherited Phase-2 fast-banking shape (the floor to beat)
        # at a safe risk/cap point matching the C1-wall3 winner.
        study.enqueue_trial({
            "tp1_r": 0.5, "tp2_r": 1.0, "tp3_r": 1.5, "c1": 0.45, "c2": 0.35,
            "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2,
            "risk_per_trade_pct": 1.0, "CORR_GROUP_CAP": 3, "MAX_TOTAL_POSITIONS": 15})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[C2w3] ladder+risk+cap optimize (3% wall) — {done} done, {remaining} remaining, "
          f"{len(cs.TRAIN_STARTS)} starts/trial, jobs={args.jobs}", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs,
                       callbacks=[make_cb(csv_path)], catch=(Exception,))

    best = study.best_trial
    print(f"\n[C2w3] BEST score={best.value:.2f}"
          f" p20={best.user_attrs.get('p20')} p30={best.user_attrs.get('p30')}"
          f" p60={best.user_attrs.get('p60')} breach={best.user_attrs.get('breach_rate')}"
          f" medTot={best.user_attrs.get('median_total')}", flush=True)
    print(f"  params: {best.params}", flush=True)
    print("[stageC2_wall3_ladder_optimize] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
