#!/usr/bin/env python3
"""
Stage 5d — JOINT (correlation-cap + risk) optimization.

Why this exists (see STAGE5C_BREACH_DIAGNOSIS.md):
  - The Stage-5c pool was optimized with CORR_GROUP_CAP OFF, so every survivor
    stacks 15-19 correlated positions and breaches the full continuous window on
    a flash/news gap. Adding the cap to those *fixed* configs breaks them
    elsewhere (Stage 5d screen: 0/6) — the cap changes the whole trade path, so
    it must be searched JOINTLY with the risk levers, not bolted on.
  - The Stage-5c optimizer also selected on six 3-4-year windows only, none of
    which is the full 2015-2024 run — so it never saw the high-funded-level
    clustering risk. This stage adds the full continuous window to the selection
    set so the objective directly rewards surviving it.

This is a thin wrapper over stage5c_oos_robust: it reuses that module's exact
risk search space, objective, penalties and CSV callback, and only:
  1. adds CORR_GROUP_CAP in {2,3,4} to the search space,
  2. appends the full 2015-2024 window to WINDOWS (selection now includes the
     continuous run the whole pool has been failing),
  3. runs an independent study/db/csv (stage5d.*), seeded from the top Stage-5c
     survivors so it starts near known-good risk and searches the cap around them.

Usage (keep alive via the Bash tool run_in_background, NO trailing &):
    uv run python3 backtest/src/stage5d_corr_cap_optimize.py [--trials 200] [--jobs 2]

NOTE: each trial now runs 7 windows incl. a ~10-min full run, so trials are
~35 min. This is a multi-session grind — the sqlite study is resumable; just
relaunch to continue.
"""
import argparse
import csv as _csv
import importlib.util
import optuna
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("stage5c_oos_robust",
                                               str(HERE / "stage5c_oos_robust.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

optuna.logging.set_verbosity(optuna.logging.WARNING)

FULL_WINDOW = ("2015-01-01", "2024-12-31")
CAP_CHOICES = [2, 3, 4]

# ── Patch 1: add CORR_GROUP_CAP to the search space (reuse 5c's risk space) ──
_orig_suggest = base._suggest


def _suggest_with_cap(trial) -> dict:
    env = _orig_suggest(trial)
    cap = trial.suggest_categorical("CORR_GROUP_CAP", CAP_CHOICES)
    env["CORR_GROUP_CAP"] = str(cap)
    return env


base._suggest = _suggest_with_cap

# ── Patch 2: selection set now includes the full continuous window ──
if FULL_WINDOW not in base.WINDOWS:
    base.WINDOWS = list(base.WINDOWS) + [FULL_WINDOW]

# ── Patch 3: log the cap column + widen net_w columns to the new window count ──
if "CORR_GROUP_CAP" not in base.PARAM_COLS:
    base.PARAM_COLS = list(base.PARAM_COLS) + ["CORR_GROUP_CAP"]
base.CSV_HEADER = (
    ["trial", "breached", "objective", "maximin", "avg_net",
     "worst_tdd", "worst_ddd", "n_survived", "fail_window"]
    + base.PARAM_COLS
    + [f"net_w{i}" for i in range(len(base.WINDOWS))]
)


def _load_stage5c_survivor_seeds(n: int) -> list[dict]:
    """Top-n non-breached Stage-5c rows -> seed dicts of the 12 risk params.
    CORR_GROUP_CAP is left unspecified so Optuna samples it around each seed."""
    csv_path = base.DOE_DIR / "stage5c.csv"
    if not csv_path.exists():
        return []
    rows = []
    with open(csv_path, newline="") as f:
        for row in _csv.DictReader(f):
            if str(row.get("breached", "True")).strip().lower() in ("true", "1"):
                continue
            try:
                rows.append((float(row["objective"]), row))
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda x: x[0], reverse=True)
    seeds = []
    risk_cols = [c for c in base.PARAM_COLS if c != "CORR_GROUP_CAP"]
    for _, row in rows[:n]:
        seed = {}
        for c in risk_cols:
            v = row.get(c, "")
            if v == "":
                break
            seed[c] = float(v)
        if len(seed) == len(risk_cols):
            seeds.append(seed)
    return seeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()

    base.DOE_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(base.DOE_DIR / "stage5d.db")
    csv_path = base.DOE_DIR / "stage5d.csv"
    base._cleanup_zombies(db_path)

    study = optuna.create_study(
        direction="maximize", study_name="stage5d",
        storage=f"sqlite:///{db_path}", load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42, multivariate=True),
    )

    non_fail = [t for t in study.trials
                if t.state != optuna.trial.TrialState.FAIL]
    if not non_fail:
        seeds = _load_stage5c_survivor_seeds(20)
        for s in seeds:
            study.enqueue_trial(s)  # cap left free -> sampled
        print(f"[stage5d] seeded {len(seeds)} Stage-5c survivor risk configs "
              f"(CORR_GROUP_CAP sampled in {CAP_CHOICES})", flush=True)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE,
                              optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[stage5d] joint cap+risk over {len(base.WINDOWS)} windows "
          f"(incl. full 2015-2024) — {done} done, {remaining} remaining, "
          f"jobs={args.jobs}", flush=True)

    if remaining > 0:
        study.optimize(
            base.objective,
            n_trials=remaining,
            n_jobs=args.jobs,
            callbacks=[base.make_csv_callback(csv_path)],
            catch=(Exception,),
        )

    survivors = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE and t.value > -1e8]
    print(f"\n[stage5d] COMPLETE — {len(survivors)} zero-breach survivors "
          f"(incl. full continuous window)", flush=True)
    if survivors:
        best = study.best_trial
        print(f"  BEST obj={best.value:,.0f}"
              f"  tdd={best.user_attrs.get('worst_tdd')}%"
              f"  ddd={best.user_attrs.get('worst_ddd')}%"
              f"  cap={best.params.get('CORR_GROUP_CAP')}"
              f"  calm={best.params.get('RISK_CALM_MULT')}"
              f"  vol={best.params.get('RISK_VOLATILE_MULT')}", flush=True)
        print(f"  env: {best.params}", flush=True)
    print("[stage5d] STAGE5D_OPTIMIZE_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
