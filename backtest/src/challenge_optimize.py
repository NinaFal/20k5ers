#!/usr/bin/env python3
"""
Stage 6 — 5%ers 2-STEP CHALLENGE optimizer (multi-variable Optuna).

Objective = pass Step 1 (+8% on a fresh 100k) as FAST as possible while keeping
the breach rate near ZERO, evaluated across many start dates. Unlike the earlier
one-variable risk sweep, this searches the full lever space jointly:

  risk_per_trade_pct, RISK_CALM_MULT, RISK_VOLATILE_MULT, VOL_REGIME_DD_OFF,
  CFG_MAX_CUM_RISK, CFG_DAILY_HALT_PCT, the 3-rung TDD ladder + risks,
  TDD_WALL_SAFETY, CORR_GROUP_CAP in {2,3,4}, and INCLUDE_CHF in {on, off}.

Entry + TP ladder are held at the proven t39 skeleton (stages 1-3 winners).

Score per trial (higher is better), across START dates on a fresh $100k:
    pass_no_breach_rate * 100          # safe passes within horizon (primary)
      - median_days_to_8pct * 0.20     # reward speed among the safe passes
      - breach_rate * 1000             # breaches are near-vetoed (safety first)

Resumable sqlite study (challenge.db). Multi-session grind — relaunch to continue.
Run (keepalive via Bash run_in_background, NO trailing &):
    uv run python3 backtest/src/challenge_optimize.py [--trials 200] [--jobs 2]
"""
import argparse, csv, importlib.util, json, os, sqlite3
from pathlib import Path
from statistics import median

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)
_c = importlib.util.spec_from_file_location("chal", str(HERE / "challenge_eval.py"))
ce = importlib.util.module_from_spec(_c); _c.loader.exec_module(ce)

os.environ.setdefault("RUN_TIMEOUT_S", "999999")

ACCOUNT = 100_000
CHF = "USD_CHF,EUR_CHF,GBP_CHF,AUD_CHF,NZD_CHF,CAD_CHF,CHF_JPY"
HORIZON_DAYS = 150
# Start dates the trial is scored on (black-swan-free years). Kept modest so a
# trial is ~12 runs; widen later for the final validation of the winner.
EVAL_STARTS = [f"{y}-{m:02d}-01" for y in (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024)
               for m in (1, 7)]

PARAM_COLS = ["risk_per_trade_pct", "RISK_CALM_MULT", "RISK_VOLATILE_MULT",
              "VOL_REGIME_DD_OFF", "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
              "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS", "CFG_TDD_WARNING_PCT",
              "CFG_RISK_CONSERVATIVE", "CFG_TDD_EMERGENCY_PCT", "CFG_RISK_ULTRASAFE",
              "TDD_WALL_SAFETY", "CORR_GROUP_CAP", "INCLUDE_CHF"]
CSV_HEADER = (["trial", "score", "pass_rate", "breach_rate", "median_days", "n_starts"]
              + PARAM_COLS)


def _suggest(trial):
    risk    = trial.suggest_float("risk_per_trade_pct", 0.6, 3.0, step=0.1)
    calm    = trial.suggest_float("RISK_CALM_MULT",     0.70, 1.50, step=0.01)
    vol     = trial.suggest_float("RISK_VOLATILE_MULT", 0.60, 1.30, step=0.01)
    regoff  = trial.suggest_float("VOL_REGIME_DD_OFF",  2.0, 5.0, step=0.5)
    cumrisk = trial.suggest_float("CFG_MAX_CUM_RISK",   2.5, 5.0, step=0.5)
    halt    = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.25, 3.5, step=0.25)
    caut    = trial.suggest_float("CFG_TDD_CAUTION_PCT", 3.0, 6.0, step=0.5)
    warn    = trial.suggest_float("CFG_TDD_WARNING_PCT", caut + 0.5, 8.0, step=0.5)
    emer    = trial.suggest_float("CFG_TDD_EMERGENCY_PCT", warn + 0.5, 9.0, step=0.5)
    rcaut   = trial.suggest_float("CFG_RISK_CAUTIOUS",  0.20, 0.80, step=0.05)
    rcons   = trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.15, min(rcaut, 0.60), step=0.05)
    rultra  = trial.suggest_float("CFG_RISK_ULTRASAFE", 0.10, min(rcons, 0.40), step=0.05)
    wall    = trial.suggest_float("TDD_WALL_SAFETY",    2.0, 5.0, step=0.5)
    cap     = trial.suggest_categorical("CORR_GROUP_CAP", [2, 3, 4])
    inc_chf = trial.suggest_categorical("INCLUDE_CHF", [0, 1])
    env = {
        "RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
        "FIVEERS_MAX_SCALE": "4000000",
        "RISK_CALM_MULT": f"{calm}", "RISK_VOLATILE_MULT": f"{vol}",
        "VOL_REGIME_DD_OFF": f"{regoff}", "CFG_MAX_CUM_RISK": f"{cumrisk}",
        "CFG_DAILY_HALT_PCT": f"{halt}", "CFG_TDD_CAUTION_PCT": f"{caut}",
        "CFG_RISK_CAUTIOUS": f"{rcaut}", "CFG_TDD_WARNING_PCT": f"{warn}",
        "CFG_RISK_CONSERVATIVE": f"{rcons}", "CFG_TDD_EMERGENCY_PCT": f"{emer}",
        "CFG_RISK_ULTRASAFE": f"{rultra}", "TDD_WALL_SAFETY": f"{wall}",
        "CORR_GROUP_CAP": f"{cap}",
    }
    if not inc_chf:
        env["EXCLUDE_SYMBOLS"] = CHF
    return env, risk


def _eval_start(env, tp, start):
    """Return (breached: bool, day_to_8pct: int|None) for one fresh-100k start."""
    from datetime import date, timedelta
    import subprocess, sys, tempfile, shutil
    s = date.fromisoformat(start)
    end = (s + timedelta(days=HORIZON_DAYS)).isoformat()
    e = dict(os.environ); e.update(dh.BASE_ENV); e.update(env)
    e["OPT_PARAMS"] = json.dumps({**dh.BASE_TP, **tp}); e["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        cmd = [sys.executable, str(dh.BACKTEST), "--start", start, "--end", end,
               "--balance", str(ACCOUNT), "--output", td, "--quiet"]
        subprocess.run(cmd, env=e, cwd=str(dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=1800)
        rj = Path(td) / "results.json"
        r = json.loads(rj.read_text()) if rj.exists() else {}
        fi = r.get("fail_info") or {}
        breached = bool(r.get("account_failed"))
        bday = None
        if breached and fi.get("time"):
            try:
                bday = (date.fromisoformat(str(fi["time"])[:10]) - s).days
            except ValueError:
                pass
        _, d8 = ce.days_to_target(Path(td) / "trades.csv", start)
        # a start "passes" only if it reaches +8% and did not breach earlier
        if d8 is not None and breached and bday is not None and bday < d8:
            d8 = None  # breach came first
        return breached, d8
    finally:
        shutil.rmtree(td, ignore_errors=True)


def objective(trial):
    env, risk = _suggest(trial)
    tp = dict(scr.TP_OVER); tp["risk_per_trade_pct"] = risk
    breaches = 0
    pass_days = []
    for start in EVAL_STARTS:
        breached, d8 = _eval_start(env, tp, start)
        if breached:
            breaches += 1
        if d8 is not None:
            pass_days.append(d8)
    n = len(EVAL_STARTS)
    pass_rate = len(pass_days) / n
    breach_rate = breaches / n
    med = median(pass_days) if pass_days else HORIZON_DAYS
    score = pass_rate * 100 - med * 0.20 - breach_rate * 1000
    trial.set_user_attr("pass_rate", round(pass_rate, 3))
    trial.set_user_attr("breach_rate", round(breach_rate, 3))
    trial.set_user_attr("median_days", med)
    return score


def make_cb(csv_path):
    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               "pass_rate": trial.user_attrs.get("pass_rate"),
               "breach_rate": trial.user_attrs.get("breach_rate"),
               "median_days": trial.user_attrs.get("median_days"),
               "n_starts": len(EVAL_STARTS),
               **{k: trial.params.get(k, "") for k in PARAM_COLS}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if new:
                w.writeheader()
            w.writerow(row)
        print(f"[chal] trial {trial.number:3d}  score={trial.value:7.2f}"
              f"  pass={trial.user_attrs.get('pass_rate')}"
              f"  breach={trial.user_attrs.get('breach_rate')}"
              f"  medDays={trial.user_attrs.get('median_days')}"
              f"  risk={trial.params.get('risk_per_trade_pct')}"
              f"  cap={trial.params.get('CORR_GROUP_CAP')}"
              f"  chf={trial.params.get('INCLUDE_CHF')}", flush=True)
    return cb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "challenge.db"); csv_path = DOE_DIR / "challenge.csv"

    study = optuna.create_study(direction="maximize", study_name="challenge",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    # Seed the known t39 challenge point (risk 2.0, cap 3, CHF excluded).
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        study.enqueue_trial({
            "risk_per_trade_pct": 2.0, "RISK_CALM_MULT": 0.87, "RISK_VOLATILE_MULT": 0.71,
            "VOL_REGIME_DD_OFF": 5.0, "CFG_MAX_CUM_RISK": 5.0, "CFG_DAILY_HALT_PCT": 1.75,
            "CFG_TDD_CAUTION_PCT": 3.5, "CFG_RISK_CAUTIOUS": 0.65, "CFG_TDD_WARNING_PCT": 4.5,
            "CFG_RISK_CONSERVATIVE": 0.6, "CFG_TDD_EMERGENCY_PCT": 8.0, "CFG_RISK_ULTRASAFE": 0.4,
            "TDD_WALL_SAFETY": 4.0, "CORR_GROUP_CAP": 3, "INCLUDE_CHF": 0})

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[chal] challenge optimize — {done} done, {remaining} remaining, "
          f"{len(EVAL_STARTS)} starts/trial, jobs={args.jobs}", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=args.jobs,
                       callbacks=[make_cb(csv_path)], catch=(Exception,))

    best = study.best_trial
    print(f"\n[chal] BEST score={best.value:.2f}  pass={best.user_attrs.get('pass_rate')}"
          f"  breach={best.user_attrs.get('breach_rate')}"
          f"  medDays={best.user_attrs.get('median_days')}", flush=True)
    print(f"  params: {best.params}", flush=True)
    print("[challenge_optimize] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
