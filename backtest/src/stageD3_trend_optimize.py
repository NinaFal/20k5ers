#!/usr/bin/env python3
"""
D3 — trend-quality risk controller Optuna (3% wall).

Front-of-attempt mechanism (unlike D2's back-half cushion, which failed
because attempts never reached the cushion): concentrate risk where the edge
actually pays — strong-trend conditions — and starve it in chop, via the new
continuous D1-ADX sizing controller (TREND_RISK_ENABLE lever; NOT a skip-gate,
which Stage 1 proved harmful).

Locked: C1-wall3 winner entry, bank_fast ladder, cap 3 / maxpos 15,
expanded_no_bleed universe (fiveers_live). Searches: ADX ramp (LO/HI), the
mult range (MULT_LO/MULT_HI), base risk, CFG_MAX_CUM_RISK.

Seeds: no-op controller (mults 1.0) = baseline floor; moderate ramp.
Resumable sqlite; single-threaded Optuna; concurrency inside objective().

Run:  uv run python3 backtest/src/stageD3_trend_optimize.py [--trials 120]
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

BASE_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_DAILY_HALT_PCT": "2.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15",
            "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
            "TREND_RISK_ENABLE": "1"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

PARAM_COLS = ["risk_per_trade_pct", "CFG_MAX_CUM_RISK",
              "TREND_ADX_LO", "TREND_ADX_HI", "TREND_MULT_LO", "TREND_MULT_HI"]
CSV_HEADER = ["trial", "score", "p20", "p30", "p40", "p60", "breach_rate", "median_total"] + PARAM_COLS


def _suggest(trial):
    risk = trial.suggest_float("risk_per_trade_pct", 0.6, 1.6, step=0.1)
    cum  = trial.suggest_float("CFG_MAX_CUM_RISK", 2.0, 6.0, step=0.5)
    lo   = trial.suggest_float("TREND_ADX_LO", 14.0, 24.0, step=2.0)
    hi   = trial.suggest_float("TREND_ADX_HI", lo + 4.0, 40.0, step=2.0)
    mlo  = trial.suggest_float("TREND_MULT_LO", 0.2, 1.0, step=0.1)
    mhi  = trial.suggest_float("TREND_MULT_HI", 1.0, 2.5, step=0.1)
    env = dict(BASE_ENV)
    env.update({"CFG_MAX_CUM_RISK": f"{cum}", "TREND_ADX_LO": f"{lo}",
                "TREND_ADX_HI": f"{hi}", "TREND_MULT_LO": f"{mlo}",
                "TREND_MULT_HI": f"{mhi}"})
    tp = dict(TP); tp["risk_per_trade_pct"] = risk
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
        print(f"[D3] trial {trial.number:3d}  score={trial.value:7.2f}"
              f"  p30={trial.user_attrs.get('p30')} p60={trial.user_attrs.get('p60')}"
              f"  breach={trial.user_attrs.get('breach_rate')}"
              f"  medTot={trial.user_attrs.get('median_total')}"
              f"  risk={trial.params.get('risk_per_trade_pct')}"
              f"  adx={trial.params.get('TREND_ADX_LO')}-{trial.params.get('TREND_ADX_HI')}"
              f"  mult={trial.params.get('TREND_MULT_LO')}-{trial.params.get('TREND_MULT_HI')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageD3.db"); csv_path = DOE_DIR / "stageD3.csv"

    study = optuna.create_study(direction="maximize", study_name="stageD3",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        study.enqueue_trial({"risk_per_trade_pct": 1.0, "CFG_MAX_CUM_RISK": 2.5,
                             "TREND_ADX_LO": 18.0, "TREND_ADX_HI": 30.0,
                             "TREND_MULT_LO": 1.0, "TREND_MULT_HI": 1.0})  # no-op floor
        study.enqueue_trial({"risk_per_trade_pct": 1.0, "CFG_MAX_CUM_RISK": 4.0,
                             "TREND_ADX_LO": 18.0, "TREND_ADX_HI": 30.0,
                             "TREND_MULT_LO": 0.5, "TREND_MULT_HI": 1.5})  # moderate ramp

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[D3] trend-controller optimize — {done} done, {remaining} remaining, "
          f"{len(cs.TRAIN_STARTS)} starts/trial", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs,
                       callbacks=[make_cb(csv_path)], catch=(Exception,))

    best = study.best_trial
    print(f"\n[D3] BEST score={best.value:.2f} p30={best.user_attrs.get('p30')}"
          f" p60={best.user_attrs.get('p60')} breach={best.user_attrs.get('breach_rate')}"
          f" medTot={best.user_attrs.get('median_total')}", flush=True)
    print(f"  params: {best.params}", flush=True)
    print("[stageD3_trend_optimize] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
