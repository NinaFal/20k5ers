#!/usr/bin/env python3
"""
Stage 4 — Pareto joint optimization of the TP/SL ladder.

Goal: find a TP/SL ladder config that is BOTH more profitable AND more robust
than the locked trial 68, i.e. sits on a wide plateau (all ±1-step perturbations
survive) while maximising worst-window net profit (maximin).

The robustness report flagged 7/12 perturbations breaching on trial 68:
  - sl_after_tp3_r=1.50 is a spike (both ±0.1 breach)
  - tp5_r=5.5 is a spike (both ±0.3 breach)
  - sl_after_tp2_r=0.60 lower edge, sl_after_tp4_r=1.90 upper edge
  - tp1_close_pct=0.15 upper edge

Search space: same TP/SL parameters as Stage 3, but the objective is
  PENALISED for every perturbation that breaches:

  objective = maximin_net − BREACH_PENALTY × n_perturb_breaches

This drives Optuna toward plateau configs (0 perturb breaches → no penalty)
that also maximise profit. A config that earns the same as trial 68 but
survives all ±1 perturbations scores strictly higher.

Concretely, for each trial we:
  1. Run the 5 training windows → compute maximin, breach-veto
  2. Run the 12 perturbations → count breaches, compute maximin of each
  3. Score = maximin − BREACH_PENALTY × n_perturb_breaches
     where BREACH_PENALTY = 15000 (one full worst-window net)

Resumable: uses an Optuna SQLite study (stage4_pareto.db). Runs
VAL_WORKERS parallel evaluations. Use watchdog_stage4_pareto.sh for
supervised restart on crash.

Usage:
  python -u backtest/src/stage4_pareto.py --trials 200
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import doe_harness as dh
from stage4_validate import WINNER_ENV, WINNER_ENTRY, TRAIN_WINDOWS

# Only the 2 hardest training windows are used for perturbation checks.
# All observed perturbation breaches occur on these two windows; the other
# 3 have never triggered a perturbation failure, so testing them adds cost
# with zero signal.  The full TRAIN_WINDOWS set still gates the base config.
PERTURB_WINDOWS = [
    ("2016-01-01", "2018-12-31"),
    ("2017-01-01", "2019-12-31"),
]

DOE_DIR      = REPO / "backtest" / "output" / "doe"
DB_PATH      = DOE_DIR / "stage4_pareto.db"
CSV_PATH     = DOE_DIR / "stage4_pareto.csv"
REPORT_PATH  = DOE_DIR / "stage4_pareto_report.txt"

BREACH_PENALTY = 15_000   # per perturbation breach, subtracted from objective
WORKERS        = int(os.getenv("VAL_WORKERS", "4"))

os.environ.setdefault("RUN_TIMEOUT_S", "999999")


# ── Locked Stage 1 entry (unchanged) ──────────────────────────────────────────
BASE_ENTRY = WINNER_ENTRY


# ── Parameter bounds ──────────────────────────────────────────────────────────
# Wider than Stage 3 so Optuna can find the plateau rather than the spike.

def suggest_params(trial: optuna.Trial) -> dict:
    tp1 = trial.suggest_float("tp1_r",  0.6,  1.2,  step=0.1)
    tp2 = trial.suggest_float("tp2_r",  1.2,  2.2,  step=0.1)
    tp3 = trial.suggest_float("tp3_r",  2.0,  3.5,  step=0.1)
    tp4 = trial.suggest_float("tp4_r",  2.8,  4.5,  step=0.1)
    tp5 = trial.suggest_float("tp5_r",  4.0,  7.0,  step=0.3)

    # Keep ordering: tp1 < tp2 < tp3 < tp4 < tp5 with minimum gaps
    if not (tp1 + 0.4 <= tp2 <= tp3 - 0.4 <= tp4 - 0.6 <= tp5 - 0.9):
        raise optuna.TrialPruned()

    c1 = trial.suggest_float("tp1_close", 0.05, 0.25, step=0.05)
    c2 = trial.suggest_float("tp2_close", 0.15, 0.40, step=0.05)
    c3 = trial.suggest_float("tp3_close", 0.10, 0.25, step=0.05)
    c4 = trial.suggest_float("tp4_close", 0.05, 0.15, step=0.05)
    # c5 is the remainder so sum=1
    c5 = round(1.0 - c1 - c2 - c3 - c4, 3)
    if c5 < 0.10 or c5 > 0.60:
        raise optuna.TrialPruned()

    sl2 = trial.suggest_float("sl_after_tp2_r", 0.50, 0.90, step=0.10)
    sl3 = trial.suggest_float("sl_after_tp3_r", 1.20, 1.90, step=0.10)
    sl4 = trial.suggest_float("sl_after_tp4_r", 1.60, 2.20, step=0.10)

    # SL trail must be monotone
    if not (sl2 + 0.3 <= sl3 <= sl4 - 0.2):
        raise optuna.TrialPruned()

    return {
        "tp1_r_multiple": tp1, "tp2_r_multiple": tp2,
        "tp3_r_multiple": tp3, "tp4_r_multiple": tp4,
        "tp5_r_multiple": tp5,
        "tp1_close_pct": c1,   "tp2_close_pct": c2,
        "tp3_close_pct": c3,   "tp4_close_pct": c4,
        "tp5_close_pct": c5,
        "sl_after_tp2_r": sl2, "sl_after_tp3_r": sl3,
        "sl_after_tp4_r": sl4,
        "risk_per_trade_pct": 0.9,
    }


def _perturbations(base: dict):
    """Yield (label, params) for each ±1-step perturbation of fragile levers."""
    for r in (0.8, 1.0):
        p = dict(base); p["risk_per_trade_pct"] = r
        yield f"risk={r}", p
    for key, delta in [
        ("sl_after_tp2_r", -0.10), ("sl_after_tp2_r", +0.10),
        ("sl_after_tp3_r", -0.10), ("sl_after_tp3_r", +0.10),
        ("sl_after_tp4_r", -0.10), ("sl_after_tp4_r", +0.10),
        ("tp5_r_multiple", -0.30), ("tp5_r_multiple", +0.30),
        ("tp1_close_pct",  -0.05), ("tp1_close_pct",  +0.05),
    ]:
        p = dict(base); p[key] = round(base[key] + delta, 3)
        yield f"{key}{delta:+.2f}", p


def run_window(params: dict, env_over: dict, start: str, end: str):
    tp = {**BASE_ENTRY, **params}
    return dh.run_single(env_over, tp, start, end)


def score_trial(params: dict) -> tuple[float, dict]:
    """
    Returns (objective, info_dict).
    objective = maximin_net - BREACH_PENALTY * n_perturb_breaches
    """
    # ── Step 1: base config on training windows ────────────────────────────
    nets, breached = [], False
    worst_tdd = 0.0
    for (s, e) in TRAIN_WINDOWS:
        r = run_window(params, WINNER_ENV, s, e)
        if r is None:
            return float("-inf"), {"error": "infra"}
        if r.get("account_failed"):
            print(f"[BREACH] {s}->{e} tdd={r.get('max_tdd_pct',0):.2f}% risk={params.get('risk_per_trade_pct',0):.1f}", flush=True)
            breached = True
            break
        nets.append(float(r.get("net_pnl") or 0))
        worst_tdd = max(worst_tdd, float(r.get("max_tdd_pct") or 0))

    if breached or not nets:
        return float("-inf"), {"breached": True}

    maximin = min(nets)
    avg_net = sum(nets) / len(nets)

    # ── Step 2: perturbation plateau check (2 hardest windows only) ──────
    n_breach = 0
    perturb_details = []
    for label, p_params in _perturbations(params):
        p_nets, p_breached = [], False
        p_worst_tdd = 0.0
        for (s, e) in PERTURB_WINDOWS:
            r = run_window(p_params, WINNER_ENV, s, e)
            if r is None or r.get("account_failed"):
                p_breached = True
                break
            p_nets.append(float(r.get("net_pnl") or 0))
            p_worst_tdd = max(p_worst_tdd, float(r.get("max_tdd_pct") or 0))
        if p_breached:
            n_breach += 1
        perturb_details.append({
            "label": label,
            "breached": p_breached,
            "maximin": min(p_nets) if p_nets else None,
            "worst_tdd": round(p_worst_tdd, 2),
        })

    objective = maximin - BREACH_PENALTY * n_breach

    info = {
        "maximin": round(maximin),
        "avg_net": round(avg_net),
        "worst_tdd": round(worst_tdd, 2),
        "n_perturb_breaches": n_breach,
        "objective": round(objective),
        "perturb": perturb_details,
        **{f"net_w{i}": round(nets[i]) for i in range(len(nets))},
    }
    return objective, info


def objective(trial: optuna.Trial) -> float:
    try:
        params = suggest_params(trial)
    except optuna.TrialPruned:
        raise

    obj, info = score_trial(params)
    if obj == float("-inf"):
        return float("-inf")

    # Store all info as trial attributes for the CSV report
    for k, v in info.items():
        if k != "perturb":
            trial.set_user_attr(k, v)
    trial.set_user_attr("params", json.dumps(params))
    trial.set_user_attr("perturb", json.dumps(info.get("perturb", [])))

    return obj


def save_csv(study: optuna.Study):
    rows = []
    for t in study.trials:
        if t.state != optuna.trial.TrialState.COMPLETE:
            continue
        row = {"trial": t.number, "objective": t.value}
        row.update(t.user_attrs)
        rows.append(row)
    if not rows:
        return
    import csv
    keys = list(rows[0].keys())
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def build_report(study: optuna.Study) -> str:
    trials = [t for t in study.trials
              if t.state == optuna.trial.TrialState.COMPLETE and t.value is not None
              and t.value > float("-inf")]
    trials.sort(key=lambda t: t.value, reverse=True)

    lines = ["=" * 78,
             "Stage 4 Pareto Report — TP/SL Plateau Optimization",
             f"Generated: {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Trials complete: {len(trials)}  "
             f"Breach penalty: ${BREACH_PENALTY:,}/perturb",
             "=" * 78, "",
             f"{'#':<4} {'trial':<6} {'obj':>9} {'maximin':>9} {'avg_net':>9} "
             f"{'wtdd':>6} {'perturb_ok':>10}  TP ladder",
             "-" * 90]

    for rank, t in enumerate(trials[:20], 1):
        ua = t.user_attrs
        params = json.loads(ua.get("params", "{}"))
        n_ok = 10 - int(ua.get("n_perturb_breaches", 10))
        tps = "/".join(f"{params.get(f'tp{i}_r_multiple', 0):.1f}"
                       for i in range(1, 6))
        lines.append(
            f"{rank:<4} {t.number:<6} {t.value:>9,.0f} "
            f"{ua.get('maximin', 0):>9,.0f} {ua.get('avg_net', 0):>9,.0f} "
            f"{ua.get('worst_tdd', 0):>5.1f}% {n_ok:>10}/10  TP={tps}")

    # Best plateau config (0 perturb breaches)
    plateaus = [t for t in trials if t.user_attrs.get("n_perturb_breaches", 99) == 0]
    if plateaus:
        best = plateaus[0]
        ua = best.user_attrs
        params = json.loads(ua.get("params", "{}"))
        lines += ["", "── Best Zero-Breach-Perturbation Config (plateau) ────────────────────",
                  f"  Trial {best.number}  obj={best.value:,.0f}  "
                  f"maximin={ua['maximin']:,}  avg_net={ua['avg_net']:,}  "
                  f"worst_tdd={ua['worst_tdd']:.2f}%",
                  "  Parameters:"]
        for k, v in params.items():
            lines.append(f"    {k}: {v}")

    lines += ["", "=" * 78, "STAGE4_PARETO_DONE_MARKER"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)

    storage = f"sqlite:///{DB_PATH}"
    study = optuna.create_study(
        study_name="stage4_pareto",
        storage=storage,
        load_if_exists=True,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42, multivariate=True),
    )

    done = len([t for t in study.trials
                if t.state == optuna.trial.TrialState.COMPLETE])
    remaining = max(0, args.trials - done)

    print(f"Stage4 Pareto: {done} done, running {remaining} more "
          f"(target {args.trials}), workers={WORKERS}")

    def _progress(study: optuna.Study, trial: optuna.trial.FrozenTrial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        done_n = len([t for t in study.trials
                      if t.state == optuna.trial.TrialState.COMPLETE])
        plateaus = sum(1 for t in study.trials
                       if t.state == optuna.trial.TrialState.COMPLETE
                       and t.user_attrs.get("n_perturb_breaches", 99) == 0)
        ua = trial.user_attrs
        print(f"[trial {trial.number:>3}] done={done_n:>3}/{args.trials}  "
              f"obj={trial.value:>10,.0f}  maximin={ua.get('maximin',0):>9,.0f}  "
              f"perturb_ok={10-int(ua.get('n_perturb_breaches',10)):>2}/10  "
              f"plateaus={plateaus}", flush=True)

    if remaining > 0:
        study.optimize(
            objective,
            n_trials=remaining,
            n_jobs=WORKERS,
            show_progress_bar=False,
            callbacks=[_progress],
            catch=(Exception,),
        )

    save_csv(study)
    report = build_report(study)
    REPORT_PATH.write_text(report)
    print(f"\n{report}")
    print(f"\nCSV:    {CSV_PATH}")
    print(f"Report: {REPORT_PATH}")
    print("STAGE4_PARETO_DONE_MARKER")


if __name__ == "__main__":
    main()
