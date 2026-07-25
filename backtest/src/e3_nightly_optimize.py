#!/usr/bin/env python3
"""
E3 — fastest ZERO-BREACH config with the overnight control tuned (3% wall).

E2 established that NIGHTLY_DERISK moves the whole speed/safety frontier
(16 TRAIN starts, matched risk, only the overnight control differing):

  risk 1.0 off : breach 25.0%  complete 25.0%  median 165d  fastest 109d
  risk 1.0 ON  : breach  6.2%  complete 68.8%  median  76d  fastest  31d
  risk 1.6 off : breach 43.8%  complete 12.5%  median  94d  fastest  49d
  risk 1.6 ON  : breach 25.0%  complete 75.0%  median  59d  fastest  18d  p40 31.2%

Every one of those used first-guess overnight defaults — none of the five knobs
had ever been searched. E3 searches them jointly with risk and the position
caps, against the user's actual criterion: FASTEST, subject to ZERO breach.

Objective: breach is a hard constraint (no amount of speed buys it back).
Among breach-free configs the score rewards passing inside 40 days first, then
completing at all, then raw median speed — matching "pass within 30/40 days".

Run:  uv run python3 backtest/src/e3_nightly_optimize.py [--trials 150]
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
WORKERS = int(os.environ.get("E3_WORKERS", str(os.cpu_count() or 2)))

BASE_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0",
            "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
            "BROKER_TYPE": "fiveers_live", "CFG_DAILY_WALL_PCT": "3.0",
            "NIGHTLY_DERISK": "1"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

PARAM_COLS = ["risk_per_trade_pct", "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
              "CORR_GROUP_CAP", "MAX_TOTAL_POSITIONS",
              "NIGHTLY_DERISK_HOUR", "NIGHTLY_MAX_PER_GROUP", "NIGHTLY_MAX_TOTAL",
              "NIGHTLY_R_CLOSE_LOSING", "NIGHTLY_R_NEW", "NIGHTLY_REDUCE_PCT"]
CSV_HEADER = ["trial", "score", "breach_rate", "complete_rate", "median_days",
              "fastest_days", "p30", "p40", "p60"] + PARAM_COLS


def _suggest(trial):
    risk = trial.suggest_float("risk_per_trade_pct", 0.8, 2.0, step=0.1)
    cum  = trial.suggest_float("CFG_MAX_CUM_RISK", 2.0, 6.0, step=0.5)
    halt = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.0, 2.5, step=0.25)
    cap  = trial.suggest_int("CORR_GROUP_CAP", 2, 5)
    maxp = trial.suggest_categorical("MAX_TOTAL_POSITIONS", [6, 8, 10, 12, 15, 20])
    # the overnight controls — the five knobs E2 left at first-guess defaults
    hour = trial.suggest_categorical("NIGHTLY_DERISK_HOUR", [17, 19, 20, 21, 22])
    npg  = trial.suggest_int("NIGHTLY_MAX_PER_GROUP", 0, 3)
    nmt  = trial.suggest_int("NIGHTLY_MAX_TOTAL", 0, 8)
    rcl  = trial.suggest_float("NIGHTLY_R_CLOSE_LOSING", -0.5, 0.5, step=0.25)
    rnew = trial.suggest_float("NIGHTLY_R_NEW", 0.25, 1.5, step=0.25)
    rpct = trial.suggest_float("NIGHTLY_REDUCE_PCT", 0.25, 1.0, step=0.25)
    env = dict(BASE_ENV)
    env.update({"CFG_MAX_CUM_RISK": f"{cum}", "CFG_DAILY_HALT_PCT": f"{halt}",
                "CORR_GROUP_CAP": f"{cap}", "MAX_TOTAL_POSITIONS": f"{maxp}",
                "NIGHTLY_DERISK_HOUR": f"{hour}", "NIGHTLY_MAX_PER_GROUP": f"{npg}",
                "NIGHTLY_MAX_TOTAL": f"{nmt}", "NIGHTLY_R_CLOSE_LOSING": f"{rcl}",
                "NIGHTLY_R_NEW": f"{rnew}", "NIGHTLY_REDUCE_PCT": f"{rpct}"})
    tp = dict(TP); tp["risk_per_trade_pct"] = risk
    return env, tp


def evaluate(env, tp, horizon):
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(cs.full_two_step, env, tp, s, horizon) for s in cs.TRAIN_STARTS]
        for fut in futs:
            r = fut.result(); r.pop("detail", None); rows.append(r)
    n = len(rows)
    totals = sorted(r["total"] for r in rows if r["total"] is not None)
    return {"breach_rate": round(sum(1 for r in rows if r["breach"]) / n, 3),
            "complete_rate": round(len(totals) / n, 3),
            "median_days": (totals[len(totals) // 2] if totals else None),
            "fastest_days": (totals[0] if totals else None),
            "p30": round(sum(1 for t in totals if t <= 30) / n, 3),
            "p40": round(sum(1 for t in totals if t <= 40) / n, 3),
            "p60": round(sum(1 for t in totals if t <= 60) / n, 3)}


def score_of(m):
    if m["breach_rate"] > 0:
        return -1e6 * m["breach_rate"]          # hard constraint
    if not m["complete_rate"]:
        return -1000.0                          # safe but never finishes
    # inside-40-days first, then completing at all, then raw speed
    return (500.0 * m["p40"] + 300.0 * m["p30"]
            + 200.0 * m["complete_rate"] - float(m["median_days"]))


def objective(trial, horizon):
    env, tp = _suggest(trial)
    m = evaluate(env, tp, horizon)
    for k, v in m.items():
        trial.set_user_attr(k, v)
    return score_of(m)


def make_cb(csv_path):
    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        ua = trial.user_attrs
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               **{k: ua.get(k) for k in ("breach_rate", "complete_rate", "median_days",
                                         "fastest_days", "p30", "p40", "p60")},
               **{k: trial.params.get(k, "") for k in PARAM_COLS}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if new: w.writeheader()
            w.writerow(row)
        flag = "SAFE" if ua.get("breach_rate") == 0.0 else f"br={ua.get('breach_rate')}"
        print(f"[E3] t{trial.number:3d} {flag:>10} p30={ua.get('p30')} p40={ua.get('p40')}"
              f" median={ua.get('median_days')} fastest={ua.get('fastest_days')}"
              f" risk={trial.params.get('risk_per_trade_pct')}"
              f" night={trial.params.get('NIGHTLY_MAX_PER_GROUP')}/"
              f"{trial.params.get('NIGHTLY_MAX_TOTAL')}@{trial.params.get('NIGHTLY_DERISK_HOUR')}h"
              f" rcl={trial.params.get('NIGHTLY_R_CLOSE_LOSING')}"
              f" red={trial.params.get('NIGHTLY_REDUCE_PCT')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=150)
    ap.add_argument("--horizon", type=int, default=90)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageE3.db"); csv_path = DOE_DIR / "stageE3.csv"

    study = optuna.create_study(direction="maximize", study_name="stageE3",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        common = {"CFG_MAX_CUM_RISK": 3.0, "CFG_DAILY_HALT_PCT": 2.0,
                  "CORR_GROUP_CAP": 3, "MAX_TOTAL_POSITIONS": 15,
                  "NIGHTLY_DERISK_HOUR": 21, "NIGHTLY_MAX_PER_GROUP": 2,
                  "NIGHTLY_MAX_TOTAL": 5, "NIGHTLY_R_CLOSE_LOSING": 0.0,
                  "NIGHTLY_R_NEW": 0.5, "NIGHTLY_REDUCE_PCT": 0.5}
        study.enqueue_trial({**common, "risk_per_trade_pct": 1.0})   # E2 safest arm
        study.enqueue_trial({**common, "risk_per_trade_pct": 1.6})   # E2 fastest arm
        # tighter overnight book — the direction that should buy back the breach
        study.enqueue_trial({**common, "risk_per_trade_pct": 1.6,
                             "NIGHTLY_MAX_PER_GROUP": 1, "NIGHTLY_MAX_TOTAL": 3,
                             "NIGHTLY_R_CLOSE_LOSING": 0.25, "NIGHTLY_REDUCE_PCT": 0.75})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[E3] fastest-safe w/ tuned overnight control — {done} done, "
          f"{remaining} remaining, horizon {args.horizon}d/step, {WORKERS} workers", flush=True)
    if remaining:
        study.optimize(lambda t: objective(t, args.horizon), n_trials=remaining,
                       n_jobs=1, callbacks=[make_cb(csv_path)], catch=(Exception,))

    safe = [t for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
            and t.user_attrs.get("breach_rate") == 0.0
            and t.user_attrs.get("median_days") is not None]
    print(f"\n[E3] {len(safe)} ZERO-BREACH trials that complete", flush=True)
    for t in sorted(safe, key=lambda t: (-(t.user_attrs.get("p40") or 0),
                                         t.user_attrs["median_days"]))[:10]:
        ua = t.user_attrs
        print(f"   t{t.number:3d} p30={ua['p30']} p40={ua['p40']} median={ua['median_days']}d "
              f"fastest={ua['fastest_days']}d complete={ua['complete_rate']}", flush=True)
    print("[e3_nightly_optimize] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
