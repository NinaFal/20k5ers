#!/usr/bin/env python3
"""
Stage C3 — risk & regime Optuna, scored against the 2-step challenge objective.

Entry locked to C1 winner (c=0.65 v=0.65 thr=1.15). TP ladder is a CATEGORICAL
choice between the two C2 candidates (peak vs plateau -- see STAGEC2_WINNER.md)
so the search can pick whichever ladder actually pairs best with a given risk
profile, rather than assuming the peak is right. Searches:

  risk_per_trade_pct, RISK_CALM_MULT, RISK_VOLATILE_MULT, VOL_REGIME_DD_OFF,
  CFG_MAX_CUM_RISK, CFG_DAILY_HALT_PCT, 3-rung TDD ladder + risks,
  TDD_WALL_SAFETY, CORR_GROUP_CAP in {2,3,4}, ladder in {peak, plateau}.

Objective = challenge_score.score_results(...) on the 16 TRAIN starts.
Resumable sqlite study. Concurrency INSIDE objective() (over the 16 starts),
NOT across trials (Optuna sqlite races under n_jobs>1 -- see C2 postmortem).

Run (keepalive, no trailing &):
    uv run python3 backtest/src/stageC3_risk_regime.py [--trials 150]
"""
import argparse, concurrent.futures, csv, importlib.util, json, os
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

# C1 winner entry, locked.
ENTRY = dict(scr.PINNED_ENTRY)
ENTRY.update({"entry_fib_level": 0.65, "entry_fib_level_volatile": 0.65,
              "fib_vol_ratio_threshold": 1.15})

# The two C2 candidates -- see STAGEC2_WINNER.md.
LADDERS = {
    "peak": {  # t4: score 174.8, isolated peak
        "tp1_r_multiple": 0.40, "tp2_r_multiple": 0.75, "tp3_r_multiple": 1.35,
        "tp4_r_multiple": 2.35, "tp5_r_multiple": 3.35,
        "tp1_close_pct": 0.50, "tp2_close_pct": 0.35, "tp3_close_pct": 0.15,
        "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
        "sl_after_tp2_r": 0.25, "sl_after_tp3_r": 0.60, "sl_after_tp4_r": 0.75,
    },
    "plateau": {  # t61: score 149.8, 6-trial robust cluster (effectively 2-TP)
        "tp1_r_multiple": 0.55, "tp2_r_multiple": 1.40, "tp3_r_multiple": 2.40,
        "tp4_r_multiple": 3.40, "tp5_r_multiple": 4.40,
        "tp1_close_pct": 0.60, "tp2_close_pct": 0.60, "tp3_close_pct": 0.0,
        "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
        "sl_after_tp2_r": 0.30, "sl_after_tp3_r": 1.30, "sl_after_tp4_r": 1.40,
    },
}

PARAM_COLS = ["risk_per_trade_pct", "RISK_CALM_MULT", "RISK_VOLATILE_MULT",
              "VOL_REGIME_DD_OFF", "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
              "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS", "CFG_TDD_WARNING_PCT",
              "CFG_RISK_CONSERVATIVE", "CFG_TDD_EMERGENCY_PCT", "CFG_RISK_ULTRASAFE",
              "TDD_WALL_SAFETY", "CORR_GROUP_CAP", "MAX_TOTAL_POSITIONS", "ladder"]
CSV_HEADER = ["trial", "score", "p20", "p40", "breach_rate", "median_total"] + PARAM_COLS


def _suggest(trial):
    # Risk range narrowed per the 3% wall probe (wall3pct_risk_probe.py):
    # >=1.0% already showed 25-50% breach with a total-position cap; the search
    # explores a bit above that (optimizer may find safety via a TIGHTER
    # MAX_TOTAL_POSITIONS at higher risk) but the old 5.0% ceiling is gone.
    risk    = trial.suggest_float("risk_per_trade_pct", 0.4, 3.0, step=0.1)
    calm    = trial.suggest_float("RISK_CALM_MULT",     0.70, 1.60, step=0.01)
    vol     = trial.suggest_float("RISK_VOLATILE_MULT", 0.50, 1.30, step=0.01)
    regoff  = trial.suggest_float("VOL_REGIME_DD_OFF",  2.0, 5.0, step=0.5)
    cumrisk = trial.suggest_float("CFG_MAX_CUM_RISK",   1.5, 4.0, step=0.5)
    # "Hard close all" proactive halt -- MUST sit below the 3% terminal wall or
    # it never fires before the breach. Range 1.0-2.8 per user request (~1.5-3%).
    halt    = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.0, 2.8, step=0.1)
    caut    = trial.suggest_float("CFG_TDD_CAUTION_PCT", 2.0, 4.0, step=0.25)
    warn    = trial.suggest_float("CFG_TDD_WARNING_PCT", caut + 0.5, 5.5, step=0.25)
    emer    = trial.suggest_float("CFG_TDD_EMERGENCY_PCT", warn + 0.5, 7.0, step=0.25)
    rcaut   = trial.suggest_float("CFG_RISK_CAUTIOUS",  0.20, 0.80, step=0.05)
    rcons   = trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.15, min(rcaut, 0.60), step=0.05)
    rultra  = trial.suggest_float("CFG_RISK_ULTRASAFE", 0.10, min(rcons, 0.40), step=0.05)
    wall    = trial.suggest_float("TDD_WALL_SAFETY",    2.0, 5.0, step=0.5)
    cap     = trial.suggest_categorical("CORR_GROUP_CAP", [2, 3, 4])
    # NEW -- total concurrent-position cap (see diag_wall3_anomaly.py): without
    # this, breadth across DIFFERENT correlation groups can still breach the
    # tight 3% wall even at low per-trade risk. CORR_GROUP_CAP alone isn't enough.
    maxpos  = trial.suggest_categorical("MAX_TOTAL_POSITIONS", [3, 4, 5, 6, 8])
    ladder  = trial.suggest_categorical("ladder", list(LADDERS.keys()))
    env = {
        "RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
        "FIVEERS_MAX_SCALE": "4000000", "MAX_TOTAL_POSITIONS": f"{maxpos}",
        "RISK_CALM_MULT": f"{calm}", "RISK_VOLATILE_MULT": f"{vol}",
        "VOL_REGIME_DD_OFF": f"{regoff}", "CFG_MAX_CUM_RISK": f"{cumrisk}",
        "CFG_DAILY_HALT_PCT": f"{halt}", "CFG_TDD_CAUTION_PCT": f"{caut}",
        "CFG_RISK_CAUTIOUS": f"{rcaut}", "CFG_TDD_WARNING_PCT": f"{warn}",
        "CFG_RISK_CONSERVATIVE": f"{rcons}", "CFG_TDD_EMERGENCY_PCT": f"{emer}",
        "CFG_RISK_ULTRASAFE": f"{rultra}", "TDD_WALL_SAFETY": f"{wall}",
        "CORR_GROUP_CAP": f"{cap}",
    }
    tp = {**ENTRY, **LADDERS[ladder], "risk_per_trade_pct": risk}
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
        print(f"[C3] trial {trial.number:3d}  score={trial.value:7.2f}"
              f"  p20={trial.user_attrs.get('p20')}  p40={trial.user_attrs.get('p40')}"
              f"  breach={trial.user_attrs.get('breach_rate')}"
              f"  medTot={trial.user_attrs.get('median_total')}"
              f"  risk={trial.params.get('risk_per_trade_pct')}"
              f"  ladder={trial.params.get('ladder')}"
              f"  cap={trial.params.get('CORR_GROUP_CAP')}"
              f"  calm={trial.params.get('RISK_CALM_MULT')}"
              f"  vol={trial.params.get('RISK_VOLATILE_MULT')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--jobs", type=int, default=1)  # keep 1 -- see C2 postmortem
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    # NEW db/study name — the search space changed materially (3% wall,
    # MAX_TOTAL_POSITIONS added, several ranges narrowed) so this is NOT
    # resumable from the old stageC3.db (7 trials, all scored under the wrong
    # 5% wall). That db is kept on disk for reference but not loaded here.
    db = str(DOE_DIR / "stageC3_wall3.db"); csv_path = DOE_DIR / "stageC3_wall3.csv"

    study = optuna.create_study(direction="maximize", study_name="stageC3_wall3",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        # Seed near the wall3pct_risk_probe.py sweet spot: low-ish risk, a real
        # total-position cap, and a halt comfortably under the 3% wall.
        for ladder in LADDERS:
            for risk in (0.8, 1.2):
                study.enqueue_trial({
                    "risk_per_trade_pct": risk, "RISK_CALM_MULT": 1.45, "RISK_VOLATILE_MULT": 0.64,
                    "VOL_REGIME_DD_OFF": 5.0, "CFG_MAX_CUM_RISK": 2.5, "CFG_DAILY_HALT_PCT": 1.75,
                    "CFG_TDD_CAUTION_PCT": 2.0, "CFG_RISK_CAUTIOUS": 0.5, "CFG_TDD_WARNING_PCT": 3.0,
                    "CFG_RISK_CONSERVATIVE": 0.3, "CFG_TDD_EMERGENCY_PCT": 5.5, "CFG_RISK_ULTRASAFE": 0.15,
                    "TDD_WALL_SAFETY": 4.0, "CORR_GROUP_CAP": 2, "MAX_TOTAL_POSITIONS": 5,
                    "ladder": ladder})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[C3] risk+regime optimize — {done} done, {remaining} remaining, "
          f"{len(cs.TRAIN_STARTS)} starts/trial, jobs={args.jobs}", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs,
                       callbacks=[make_cb(csv_path)], catch=(Exception,))

    best = study.best_trial
    print(f"\n[C3] BEST score={best.value:.2f} p20={best.user_attrs.get('p20')}"
          f" p40={best.user_attrs.get('p40')} breach={best.user_attrs.get('breach_rate')}"
          f" medTot={best.user_attrs.get('median_total')}", flush=True)
    print(f"  params: {best.params}", flush=True)
    print("[stageC3_risk_regime] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
