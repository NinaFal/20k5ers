#!/usr/bin/env python3
"""
MULTI-START robust optimizer — max profit with ZERO breaches across ANY start.

WHY
---
Optimizing on the single 2015->2024 path curve-fit a $1.9M winner that breached
when started in 2016/2017. The real meaning of "0 breaches" is: survive
whatever regime exists when you actually go live. So every trial is scored on
the WORST of several continuous start dates, and a breach on ANY of them
(TDD>=10% total OR DDD>=5% daily) floors the trial.

Diagnosis that shaped the search:
  • 2017-start = TOTAL-DD bleed from calm-regime size-up + clustered exposure.
    Throttling alone just moves the breach to another year (T1-T3). The
    correlation cap (clustered-exposure lever) actually fixed 2017 (T4).
  • 2016-start = DAILY-DD spike (correlated positions gap together in one day).
  • These need DIFFERENT levers -> search them JOINTLY: vol multipliers,
    correlation cap, TDD rungs, wall-safety, and TP family.

Efficiency: starts are evaluated worst-first (2016, 2017) with EARLY EXIT — a
trial that breaches the first start costs one run, not four.

Resumable (Optuna SQLite). Run via the same supervisor/watchdog pattern.
Usage: python3 backtest/src/optimize_multistart.py --trials 60 --jobs 2
"""
import argparse, importlib.util, json, os, time
from pathlib import Path
import optuna

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("oc", str(HERE / "optimize_continuous.py"))
oc = importlib.util.module_from_spec(spec); spec.loader.exec_module(oc)

END = "2024-12-31"
# Worst-first for early exit: 2016 (daily killer) & 2017 (total killer) first.
STARTS = ["2016-01-01", "2017-01-01", "2018-01-01", "2015-01-01"]
WALL_MARGIN = float(os.getenv("WALL_MARGIN_START", "8.5"))
MARGIN_K = float(os.getenv("MARGIN_K", "30000"))

TP40 = dict(oc.TP40)
NEWTP = {"tp1_r_multiple": 0.9, "tp2_r_multiple": 1.7, "tp3_r_multiple": 2.4,
         "tp4_r_multiple": 3.4, "tp5_r_multiple": 4.7, "tp1_close_pct": 0.10,
         "tp2_close_pct": 0.35, "tp3_close_pct": 0.15, "tp4_close_pct": 0.10,
         "tp5_close_pct": 0.30, "sl_after_tp2_r": 0.7, "sl_after_tp3_r": 1.6,
         "sl_after_tp4_r": 2.0}


def build(trial):
    tp = NEWTP if trial.suggest_categorical("tp", ["newtp", "opt40"]) == "newtp" else TP40
    caut = trial.suggest_float("caut", 3.0, 5.5, step=0.5)
    warn = trial.suggest_float("warn", caut + 0.5, 7.5, step=0.5)
    emrg = trial.suggest_float("emrg", warn + 0.5, 9.0, step=0.5)
    rc = trial.suggest_float("rc", 0.30, 0.70, step=0.05)
    rco = trial.suggest_float("rco", 0.20, min(rc, 0.50), step=0.05)
    ru = trial.suggest_float("ru", 0.10, min(rco, 0.30), step=0.05)
    ws = trial.suggest_float("ws", 2.5, 5.0, step=0.5)
    vlo = trial.suggest_float("vlo", 1.0, 1.8, step=0.1)
    vhi = trial.suggest_float("vhi", 0.2, 0.7, step=0.1)
    if vlo < vhi:
        raise optuna.TrialPruned()
    cap = trial.suggest_categorical("cap", [0, 2, 3, 4])
    env = {"CFG_TDD_CAUTION_PCT": str(caut), "CFG_RISK_CAUTIOUS": str(rc),
           "CFG_TDD_WARNING_PCT": str(warn), "CFG_RISK_CONSERVATIVE": str(rco),
           "CFG_TDD_EMERGENCY_PCT": str(emrg), "CFG_RISK_ULTRASAFE": str(ru),
           "TDD_WALL_SAFETY": str(ws), "VOL_SIZE_ENABLE": "1",
           "VOL_SIZE_MULT_LOW": str(vlo), "VOL_SIZE_MULT_HIGH": str(vhi),
           "CORR_GROUP_CAP": str(cap)}
    return env, tp


def objective(trial):
    try:
        env, tp = build(trial)
    except optuna.TrialPruned:
        raise
    nets, worst_tdd = [], 0.0
    for start in STARTS:                       # worst-first; early-exit on breach
        try:
            a = oc.attrs(oc.run(env, tp, start=start, end=END))
        except Exception as e:
            trial.set_user_attr("error", repr(e)[:200]); return -3e9
        if a["failed"]:
            trial.set_user_attr("env", env); trial.set_user_attr("tp", tp)
            trial.set_user_attr("fail_start", start)
            trial.set_user_attr("fail_type", "TOTAL" if a["max_tdd"] >= 9.9 else "DAILY")
            trial.set_user_attr("n_survived_starts", len(nets))
            return -1e9 + len(nets) * 1e6 + float(a["survived_days"] or 0) * 100
        nets.append(a["net"]); worst_tdd = max(worst_tdd, a["max_tdd"])
        trial.set_user_attr(f"net_{start[:4]}", a["net"])
    trial.set_user_attr("env", env); trial.set_user_attr("tp", tp)
    trial.set_user_attr("min_net", min(nets)); trial.set_user_attr("worst_tdd", worst_tdd)
    trial.set_user_attr("n_survived_starts", len(STARTS))
    return min(nets) - MARGIN_K * max(0.0, worst_tdd - WALL_MARGIN) ** 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_multistart.db")
    ap.add_argument("--study", default="multistart_v1")
    args = ap.parse_args()

    study = optuna.create_study(direction="maximize", study_name=args.study,
                                storage=args.storage, load_if_exists=True)
    if not study.trials:                       # warm-start from the closest configs
        study.enqueue_trial({"tp": "newtp", "caut": 3.5, "warn": 5.5, "emrg": 7.0,
            "rc": 0.35, "rco": 0.20, "ru": 0.15, "ws": 4.0, "vlo": 1.3, "vhi": 0.3, "cap": 0})  # T3
        study.enqueue_trial({"tp": "newtp", "caut": 4.0, "warn": 6.0, "emrg": 7.5,
            "rc": 0.40, "rco": 0.25, "ru": 0.20, "ws": 3.5, "vlo": 1.7, "vhi": 0.4, "cap": 2})  # T4
        study.enqueue_trial({"tp": "newtp", "caut": 4.0, "warn": 6.0, "emrg": 7.5,
            "rc": 0.40, "rco": 0.25, "ru": 0.20, "ws": 3.5, "vlo": 1.4, "vhi": 0.3, "cap": 3})
        study.enqueue_trial({"tp": "opt40", "caut": 4.0, "warn": 6.5, "emrg": 8.0,
            "rc": 0.45, "rco": 0.30, "ru": 0.20, "ws": 4.0, "vlo": 1.3, "vhi": 0.3, "cap": 2})

    finished = sum(1 for t in study.trials if t.state in
                   (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - finished)
    print(f"multistart: {finished} done, running {remaining} more (target {args.trials})", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs)

    done = [t for t in study.trials if t.value is not None]
    robust = [t for t in done if t.user_attrs.get("n_survived_starts") == len(STARTS)]
    print(f"\n{len(done)} trials | {len(robust)} ROBUST (survive all {len(STARTS)} starts)", flush=True)
    print(f"{'':2}{'min_net':>12}{'worst_tdd':>10}  starts: 2015/2016/2017/2018")
    for t in sorted(robust, key=lambda t: t.user_attrs.get("min_net", 0), reverse=True)[:10]:
        a = t.user_attrs
        ns = "/".join(f"{a.get('net_'+y, 0)/1000:.0f}k" for y in ["2015", "2016", "2017", "2018"])
        print(f"  ${a['min_net']:>11,.0f}{a['worst_tdd']:>10}  {ns} | "
              f"tp={t.params['tp']} vlo={t.params['vlo']} vhi={t.params['vhi']} cap={t.params['cap']} "
              f"rungs {t.params['caut']}/{t.params['warn']}/{t.params['emrg']}", flush=True)
    if robust:
        best = max(robust, key=lambda t: t.user_attrs.get("min_net", 0))
        Path("/tmp/multistart_best.json").write_text(json.dumps(
            {"env": best.user_attrs["env"], "tp": best.user_attrs["tp"],
             "min_net": best.user_attrs["min_net"], "worst_tdd": best.user_attrs["worst_tdd"]}, indent=2))
        print(f"\nBEST ROBUST: worst-start ${best.user_attrs['min_net']:,.0f} "
              f"{'>= $1M ✓' if best.user_attrs['min_net']>=1e6 else '< $1M'}", flush=True)
    else:
        # show how far the best got
        best = max(done, key=lambda t: t.value)
        print(f"\nNo fully-robust config yet. Best reached {best.user_attrs.get('n_survived_starts')}/"
              f"{len(STARTS)} starts, failed {best.user_attrs.get('fail_start')} "
              f"({best.user_attrs.get('fail_type')})", flush=True)
    print("MULTISTART DONE", flush=True)


if __name__ == "__main__":
    main()
