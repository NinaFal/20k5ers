#!/usr/bin/env python3
"""
D2+D3 combined — cushion ratchet x trend controller joint Optuna (3% wall).

Individually (D2_D3_FINDINGS.md): the mild cushion ratchet (D2 t117) removed
the floor's one breach at unchanged speed; the trend controller (D3) also
removed breaches but braked away the one completing window. They shape
different halves of an attempt (trend = front, cushion = back), so a joint
search looks for the combination that keeps 0% breach while ADDING speed —
e.g. an up-ramped trend mult made safe by the cushion gate + drawdown gates.

Locked: C1-wall3 winner entry, bank_fast ladder, cap 3 / maxpos 15,
expanded_no_bleed universe. Searches both levers' params + risk + cum cap.
Seeds: D2 t117 exact (trend no-op) = current best; t117 + D3-best brake ramp;
t117 + moderate up-ramp.

Run:  uv run python3 backtest/src/stageD23_combined_optimize.py [--trials 120]
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
            "CUSHION_RATCHET_ENABLE": "1", "TREND_RISK_ENABLE": "1"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

PARAM_COLS = ["risk_per_trade_pct", "CFG_MAX_CUM_RISK",
              "CUSHION_DD_OFF", "CUSHION_T1", "CUSHION_M1", "CUSHION_T2", "CUSHION_M2",
              "CUSHION_T3", "CUSHION_M3",
              "TREND_ADX_LO", "TREND_ADX_HI", "TREND_MULT_LO", "TREND_MULT_HI"]
CSV_HEADER = ["trial", "score", "p20", "p30", "p40", "p60", "breach_rate", "median_total"] + PARAM_COLS


def _suggest(trial):
    risk   = trial.suggest_float("risk_per_trade_pct", 0.7, 1.4, step=0.1)
    cum    = trial.suggest_float("CFG_MAX_CUM_RISK", 2.0, 5.0, step=0.5)
    dd_off = trial.suggest_float("CUSHION_DD_OFF", 0.75, 1.5, step=0.25)
    t1 = trial.suggest_float("CUSHION_T1", 1.0, 3.5, step=0.25)
    m1 = trial.suggest_float("CUSHION_M1", 1.0, 1.6, step=0.1)
    t2 = trial.suggest_float("CUSHION_T2", t1 + 0.5, 5.0, step=0.25)
    m2 = trial.suggest_float("CUSHION_M2", m1, 2.2, step=0.1)
    t3 = trial.suggest_float("CUSHION_T3", t2 + 0.5, 7.0, step=0.25)
    m3 = trial.suggest_float("CUSHION_M3", m2, 3.0, step=0.1)
    alo = trial.suggest_float("TREND_ADX_LO", 14.0, 24.0, step=2.0)
    ahi = trial.suggest_float("TREND_ADX_HI", alo + 4.0, 38.0, step=2.0)
    mlo = trial.suggest_float("TREND_MULT_LO", 0.3, 1.0, step=0.1)
    mhi = trial.suggest_float("TREND_MULT_HI", 1.0, 2.2, step=0.1)
    env = dict(BASE_ENV)
    env.update({"CFG_MAX_CUM_RISK": f"{cum}", "CUSHION_DD_OFF": f"{dd_off}",
                "CUSHION_T1": f"{t1}", "CUSHION_M1": f"{m1}",
                "CUSHION_T2": f"{t2}", "CUSHION_M2": f"{m2}",
                "CUSHION_T3": f"{t3}", "CUSHION_M3": f"{m3}",
                "TREND_ADX_LO": f"{alo}", "TREND_ADX_HI": f"{ahi}",
                "TREND_MULT_LO": f"{mlo}", "TREND_MULT_HI": f"{mhi}"})
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
        print(f"[D23] trial {trial.number:3d}  score={trial.value:7.2f}"
              f"  p30={trial.user_attrs.get('p30')} p60={trial.user_attrs.get('p60')}"
              f"  breach={trial.user_attrs.get('breach_rate')}"
              f"  medTot={trial.user_attrs.get('median_total')}"
              f"  risk={trial.params.get('risk_per_trade_pct')}"
              f"  M={trial.params.get('CUSHION_M1')}/{trial.params.get('CUSHION_M2')}/{trial.params.get('CUSHION_M3')}"
              f"  adx={trial.params.get('TREND_ADX_LO')}-{trial.params.get('TREND_ADX_HI')}"
              f"  tmult={trial.params.get('TREND_MULT_LO')}-{trial.params.get('TREND_MULT_HI')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageD23.db"); csv_path = DOE_DIR / "stageD23.csv"

    study = optuna.create_study(direction="maximize", study_name="stageD23",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        t117 = {"risk_per_trade_pct": 1.0, "CFG_MAX_CUM_RISK": 2.5, "CUSHION_DD_OFF": 1.5,
                "CUSHION_T1": 3.0, "CUSHION_M1": 1.1, "CUSHION_T2": 3.75, "CUSHION_M2": 1.2,
                "CUSHION_T3": 5.75, "CUSHION_M3": 1.4}
        # Seed 1: D2 t117 with trend no-op (current best; floor to beat)
        study.enqueue_trial({**t117, "TREND_ADX_LO": 18.0, "TREND_ADX_HI": 30.0,
                             "TREND_MULT_LO": 1.0, "TREND_MULT_HI": 1.0})
        # Seed 2: t117 + D3's best brake ramp
        study.enqueue_trial({**t117, "TREND_ADX_LO": 24.0, "TREND_ADX_HI": 34.0,
                             "TREND_MULT_LO": 0.6, "TREND_MULT_HI": 1.0})
        # Seed 3: t117 + moderate up-ramp (the hoped-for combination)
        study.enqueue_trial({**t117, "TREND_ADX_LO": 18.0, "TREND_ADX_HI": 30.0,
                             "TREND_MULT_LO": 0.6, "TREND_MULT_HI": 1.6})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[D23] combined cushion+trend optimize — {done} done, {remaining} remaining, "
          f"{len(cs.TRAIN_STARTS)} starts/trial", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs,
                       callbacks=[make_cb(csv_path)], catch=(Exception,))

    best = study.best_trial
    print(f"\n[D23] BEST score={best.value:.2f} p30={best.user_attrs.get('p30')}"
          f" p60={best.user_attrs.get('p60')} breach={best.user_attrs.get('breach_rate')}"
          f" medTot={best.user_attrs.get('median_total')}", flush=True)
    print(f"  params: {best.params}", flush=True)
    print("[stageD23_combined_optimize] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
