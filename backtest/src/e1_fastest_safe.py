#!/usr/bin/env python3
"""
E1 — fastest ZERO-BREACH config for the 3% Summer Edition wall.

Why this is a new search and not a rerun. Every prior stage optimized

    score = 2*p20 + 3*p30 + 1*p60 - 10*breach - median/100

For a SAFE config p20=p30=p60=0, so that collapses to -median/100: going from
120 days to 67 moves the score by 0.53, while avoiding one breach moves it by
~60. The speed signal among safe configs was ~100x weaker than the breach
signal, so TPE spent its whole budget avoiding breaches and essentially none
finding FAST safe ones. "Fastest no-breach" was never actually the objective.

E1 makes it the objective:
  * breach is a HARD constraint — any breach scores -1e6 scaled by its rate,
    so no amount of speed can buy a breach back.
  * among breach-free configs, the score is dominated by how MANY start windows
    complete, then by how FAST the median completion is. Both terms are on a
    comparable scale, so the sampler gets real gradient on speed.
  * the per-step horizon is widened (default 90) so a config that genuinely
    finishes on day 75 is measured instead of being censored into a "failure" —
    at horizon 60 real speed differences are invisible.

Searched: base risk, cumulative-risk cap, position caps, the cushion ratchet
(the one lever that demonstrably removed breaches), and the daily halt.

Run:  uv run python3 backtest/src/e1_fastest_safe.py [--trials 150] [--horizon 90]
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
WORKERS = int(os.environ.get("E1_WORKERS", str(os.cpu_count() or 2)))

BASE_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0",
            "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
            "BROKER_TYPE": "fiveers_live", "CFG_DAILY_WALL_PCT": "3.0",
            "CUSHION_RATCHET_ENABLE": "1"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

PARAM_COLS = ["risk_per_trade_pct", "CFG_MAX_CUM_RISK", "CORR_GROUP_CAP",
              "MAX_TOTAL_POSITIONS", "CFG_DAILY_HALT_PCT",
              "CUSHION_DD_OFF", "CUSHION_T1", "CUSHION_M1",
              "CUSHION_T2", "CUSHION_M2", "CUSHION_T3", "CUSHION_M3"]
CSV_HEADER = ["trial", "score", "complete_rate", "median_days", "fastest_days",
              "breach_rate", "p40", "p60"] + PARAM_COLS


def _suggest(trial):
    risk = trial.suggest_float("risk_per_trade_pct", 0.5, 1.6, step=0.1)
    cum  = trial.suggest_float("CFG_MAX_CUM_RISK", 1.5, 5.0, step=0.5)
    cap  = trial.suggest_int("CORR_GROUP_CAP", 2, 5)
    maxp = trial.suggest_categorical("MAX_TOTAL_POSITIONS", [4, 6, 8, 10, 12, 15, 20])
    halt = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.0, 2.5, step=0.25)
    dd_off = trial.suggest_float("CUSHION_DD_OFF", 0.75, 2.0, step=0.25)
    t1 = trial.suggest_float("CUSHION_T1", 0.5, 3.5, step=0.25)
    m1 = trial.suggest_float("CUSHION_M1", 1.0, 1.8, step=0.1)
    t2 = trial.suggest_float("CUSHION_T2", t1 + 0.5, 5.5, step=0.25)
    m2 = trial.suggest_float("CUSHION_M2", m1, 2.4, step=0.1)
    t3 = trial.suggest_float("CUSHION_T3", t2 + 0.5, 7.5, step=0.25)
    m3 = trial.suggest_float("CUSHION_M3", m2, 3.0, step=0.1)
    env = dict(BASE_ENV)
    env.update({"CFG_MAX_CUM_RISK": f"{cum}", "CORR_GROUP_CAP": f"{cap}",
                "MAX_TOTAL_POSITIONS": f"{maxp}", "CFG_DAILY_HALT_PCT": f"{halt}",
                "CUSHION_DD_OFF": f"{dd_off}",
                "CUSHION_T1": f"{t1}", "CUSHION_M1": f"{m1}",
                "CUSHION_T2": f"{t2}", "CUSHION_M2": f"{m2}",
                "CUSHION_T3": f"{t3}", "CUSHION_M3": f"{m3}"})
    tp = dict(TP); tp["risk_per_trade_pct"] = risk
    return env, tp


def evaluate(env, tp, horizon):
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(cs.full_two_step, env, tp, s, horizon) for s in cs.TRAIN_STARTS]
        for fut in futs:
            r = fut.result(); r.pop("detail", None); rows.append(r)
    n = len(rows)
    breach = sum(1 for r in rows if r["breach"]) / n
    totals = sorted(r["total"] for r in rows if r["total"] is not None)
    comp = len(totals) / n
    med = (totals[len(totals) // 2] if totals else None)
    return {"rows": rows, "breach_rate": round(breach, 3),
            "complete_rate": round(comp, 3),
            "median_days": med, "fastest_days": (totals[0] if totals else None),
            "p40": round(sum(1 for t in totals if t <= 40) / n, 3),
            "p60": round(sum(1 for t in totals if t <= 60) / n, 3)}


def score_of(m, horizon):
    """Breach is a hard constraint; among safe configs, completions then speed."""
    if m["breach_rate"] > 0:
        return -1e6 * m["breach_rate"]
    if not m["complete_rate"]:
        return -1000.0                       # safe but never finishes
    # 200 pts for completing everywhere, minus the median day count.
    return 200.0 * m["complete_rate"] - float(m["median_days"])


def objective(trial, horizon):
    env, tp = _suggest(trial)
    m = evaluate(env, tp, horizon)
    for k in ("complete_rate", "median_days", "fastest_days", "breach_rate", "p40", "p60"):
        trial.set_user_attr(k, m[k])
    return score_of(m, horizon)


def make_cb(csv_path):
    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        ua = trial.user_attrs
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               **{k: ua.get(k) for k in ("complete_rate", "median_days", "fastest_days",
                                         "breach_rate", "p40", "p60")},
               **{k: trial.params.get(k, "") for k in PARAM_COLS}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if new: w.writeheader()
            w.writerow(row)
        flag = "SAFE" if ua.get("breach_rate") == 0.0 else f"breach={ua.get('breach_rate')}"
        print(f"[E1] t{trial.number:3d} score={trial.value:9.2f} {flag:>14}"
              f"  complete={ua.get('complete_rate')}  median={ua.get('median_days')}"
              f"  fastest={ua.get('fastest_days')}"
              f"  risk={trial.params.get('risk_per_trade_pct')}"
              f"  cap={trial.params.get('CORR_GROUP_CAP')}"
              f"/{trial.params.get('MAX_TOTAL_POSITIONS')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--horizon", type=int, default=90)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageE1.db"); csv_path = DOE_DIR / "stageE1.csv"

    study = optuna.create_study(direction="maximize", study_name="stageE1",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        # D2 t117 — the incumbent fastest safe config (day 68)
        study.enqueue_trial({"risk_per_trade_pct": 1.0, "CFG_MAX_CUM_RISK": 2.5,
                             "CORR_GROUP_CAP": 3, "MAX_TOTAL_POSITIONS": 15,
                             "CFG_DAILY_HALT_PCT": 2.0, "CUSHION_DD_OFF": 1.5,
                             "CUSHION_T1": 3.0, "CUSHION_M1": 1.1,
                             "CUSHION_T2": 3.75, "CUSHION_M2": 1.2,
                             "CUSHION_T3": 5.75, "CUSHION_M3": 1.4})
        # D2 t40 — lower risk, median 67d
        study.enqueue_trial({"risk_per_trade_pct": 0.6, "CFG_MAX_CUM_RISK": 2.5,
                             "CORR_GROUP_CAP": 3, "MAX_TOTAL_POSITIONS": 15,
                             "CFG_DAILY_HALT_PCT": 2.0, "CUSHION_DD_OFF": 1.5,
                             "CUSHION_T1": 2.0, "CUSHION_M1": 1.3,
                             "CUSHION_T2": 3.0, "CUSHION_M2": 1.6,
                             "CUSHION_T3": 4.5, "CUSHION_M3": 2.0})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[E1] fastest-safe search — {done} done, {remaining} remaining, "
          f"horizon {args.horizon}d/step, {WORKERS} workers", flush=True)
    if remaining:
        study.optimize(lambda t: objective(t, args.horizon), n_trials=remaining,
                       n_jobs=1, callbacks=[make_cb(csv_path)], catch=(Exception,))

    safe = [t for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
            and t.user_attrs.get("breach_rate") == 0.0
            and t.user_attrs.get("median_days") is not None]
    print(f"\n[E1] {len(safe)} zero-breach trials that complete", flush=True)
    for t in sorted(safe, key=lambda t: t.user_attrs["median_days"])[:10]:
        ua = t.user_attrs
        print(f"   t{t.number:3d} median={ua['median_days']}d fastest={ua['fastest_days']}d "
              f"complete={ua['complete_rate']} p60={ua['p60']}", flush=True)
    print("[e1_fastest_safe] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
