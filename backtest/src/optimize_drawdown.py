#!/usr/bin/env python3
"""
Optuna sweep over the drawdown-recovery / correlation-cap settings.

Goal: find the configuration that best SURVIVES the 10% total-drawdown wall (the
recurring killer in v6-v12) and, among survivors, recovers/compounds best.

Each trial runs the full backtest over a fixed window (default 2015-2019, which
spans the 2017 death zone plus recovery runway) with TERMINAL_ON_BREACH=1 so a
breach ends the run. Tunable knobs (all env-gated, default = current behavior):
  CORR_GROUP_CAP        max concurrent open+pending positions per correlation grp
  CFG_TDD_CAUTION_PCT   TDD level where risk first throttles to "cautious"
  CFG_RISK_CAUTIOUS     risk% in the caution band
  CFG_TDD_WARNING_PCT   TDD level for the "conservative" rung
  CFG_RISK_CONSERVATIVE risk% in the conservative band
  CFG_TDD_EMERGENCY_PCT TDD level for the "ultra-safe" rung
  CFG_RISK_ULTRASAFE    risk% in the ultra-safe band
  TDD_EMERGENCY_HALT    1=hard no-trade halt at emergency level, 0=keep trading

Objective (maximize):
  survivor:  1_000_000 + final_funded + withdrawn        (always beats a death)
  death:     survived_days*100 + funded_at_failure        (later/higher = better)

Usage:
  python3 backtest/src/optimize_drawdown.py --trials 50 --jobs 3
"""
import argparse, json, os, subprocess, sys, tempfile, math
from pathlib import Path
import optuna

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"
REPO = HERE.parent.parent

START = os.getenv("OPT_START", "2015-01-01")
END   = os.getenv("OPT_END",   "2019-12-31")
BAL   = os.getenv("OPT_BAL",   "50000")


def run_trial_config(env_overrides: dict) -> dict:
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["TERMINAL_ON_BREACH"] = "1"
        # realistic execution model (v10/v12): limit entries frictionless, stops slip
        env.setdefault("SLIPPAGE_PIPS", "0.5")
        env.setdefault("GAP_FILLS", "1")
        env.update({k: str(v) for k, v in env_overrides.items()})
        cmd = [sys.executable, str(BACKTEST),
               "--start", START, "--end", END, "--balance", BAL,
               "--output", td]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
        rj = Path(td) / "results.json"
        if proc.returncode != 0 or not rj.exists():
            return {"error": proc.returncode, "stderr": proc.stderr[-500:]}
        return json.loads(rj.read_text())


def objective(trial: optuna.Trial) -> float:
    cap = trial.suggest_categorical("corr_group_cap", [0, 1, 2, 3, 4, 6])
    caution_tdd = trial.suggest_float("cfg_tdd_caution_pct", 2.0, 5.0, step=0.5)
    risk_cautious = trial.suggest_float("cfg_risk_cautious", 0.25, 1.10, step=0.05)
    warning_tdd = trial.suggest_float("cfg_tdd_warning_pct", 4.0, 7.0, step=0.5)
    risk_conservative = trial.suggest_float("cfg_risk_conservative", 0.20, 0.80, step=0.05)
    emergency_tdd = trial.suggest_float("cfg_tdd_emergency_pct", 6.0, 9.0, step=0.5)
    risk_ultrasafe = trial.suggest_float("cfg_risk_ultrasafe", 0.10, 0.50, step=0.05)
    halt = trial.suggest_categorical("tdd_emergency_halt", [0, 1])

    # keep the ladder monotonic (caution <= warning <= emergency), else prune
    if not (caution_tdd <= warning_tdd <= emergency_tdd):
        raise optuna.TrialPruned()

    env = {
        "CORR_GROUP_CAP": cap,
        "CFG_TDD_CAUTION_PCT": caution_tdd,
        "CFG_RISK_CAUTIOUS": risk_cautious,
        "CFG_TDD_WARNING_PCT": warning_tdd,
        "CFG_RISK_CONSERVATIVE": risk_conservative,
        "CFG_TDD_EMERGENCY_PCT": emergency_tdd,
        "CFG_RISK_ULTRASAFE": risk_ultrasafe,
        "TDD_EMERGENCY_HALT": halt,
    }
    r = run_trial_config(env)
    if "error" in r:
        # failed run: worst possible score
        return -1e9

    failed = bool(r.get("account_failed"))
    fi = r.get("fail_info") or {}
    funded = float(r.get("fiveers_final_funded_level") or 0)
    withdrawn = float(r.get("fiveers_total_withdrawn") or 0)
    max_tdd = float(r.get("max_tdd_pct") or 0)

    # record useful attrs
    trial.set_user_attr("failed", failed)
    trial.set_user_attr("survived_days", fi.get("survived_days"))
    trial.set_user_attr("funded_at_failure", fi.get("funded_level_at_failure"))
    trial.set_user_attr("final_funded", funded)
    trial.set_user_attr("withdrawn", withdrawn)
    trial.set_user_attr("max_tdd", max_tdd)
    trial.set_user_attr("total_trades", r.get("total_trades"))
    trial.set_user_attr("win_rate", r.get("win_rate"))

    if not failed:
        # survivor: big base + reward growth & payouts
        return 1_000_000.0 + funded + withdrawn
    else:
        days = float(fi.get("survived_days") or 0)
        ff = float(fi.get("funded_level_at_failure") or 0)
        return days * 100.0 + ff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_dd.db")
    ap.add_argument("--study", default="dd_recovery")
    ap.add_argument("--out", default="/tmp/optuna_dd_results.json")
    args = ap.parse_args()

    study = optuna.create_study(
        direction="maximize",
        study_name=args.study,
        storage=args.storage,
        load_if_exists=True,
    )
    study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs)

    print("\n" + "=" * 70)
    print("BEST TRIAL")
    print("=" * 70)
    bt = study.best_trial
    print("score:", bt.value)
    print("params:", json.dumps(bt.params, indent=2))
    print("attrs:", json.dumps(bt.user_attrs, indent=2))

    survivors = [t for t in study.trials
                 if t.user_attrs.get("failed") is False]
    print(f"\nSURVIVORS: {len(survivors)} / {len([t for t in study.trials if t.value is not None])} completed")

    rows = []
    for t in study.trials:
        if t.value is None:
            continue
        rows.append({"number": t.number, "score": t.value,
                     "params": t.params, **t.user_attrs})
    Path(args.out).write_text(json.dumps(rows, indent=2))
    print(f"All trials written to {args.out}")


if __name__ == "__main__":
    main()
