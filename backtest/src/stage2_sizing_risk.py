#!/usr/bin/env python3
"""
Stage 2 — Sizing, risk & breach control (Optuna).

Redesigned for REGIME-COHERENT RISK (2026-06-09):
  Stage 1 proved ADX hurts as a skip-gate but ATR(14)/ATR(50) is a strong
  regime classifier (used for entry fib depth). The same signal now drives risk:
    calm regime  (ratio < thr) → RISK_CALM_MULT × BASE_RISK
    volatile     (ratio >= thr) → RISK_VOLATILE_MULT × BASE_RISK
  This replaces VOL_SIZE (ATR percentile), which was incoherent with entry.

SEARCH SPACE:
  Regime-coherent risk:
    RISK_CALM_MULT    [0.50, 1.50]   — base × mult in calm (shallow entry)
    RISK_VOLATILE_MULT[0.40, 1.80]   — base × mult in volatile (deep entry)
  Drawdown-gate for size-up:
    VOL_REGIME_DD_OFF [2.0, 5.0]     — collapse size-up once TDD/DDD >= this %
  TDD drawdown ladder (4 rungs):
    CFG_TDD_CAUTION_PCT / CFG_RISK_CAUTIOUS
    CFG_TDD_WARNING_PCT / CFG_RISK_CONSERVATIVE
    CFG_TDD_EMERGENCY_PCT / CFG_RISK_ULTRASAFE
    TDD_WALL_SAFETY (room-cap factor)
  Circuit-breakers:
    CFG_DAILY_HALT_PCT [1.5, 3.5]
    CFG_MAX_CUM_RISK   [2.5, 5.0]

BASE_RISK = 1.1% (fixed Stage 1 anchor — reproduces Stage 1 bit-for-bit when
  both mults = 1.0).

OBJECTIVE (priority order):
  1. Never breach → any window breach = hard veto (-1e9 + n_survived×1e6)
  2. Maximize maximin net (worst-window net PnL)
  3. Penalise wall-hugging (worst-window TDD > WALL_MARGIN)

Resumable: Optuna sqlite (load_if_exists). Wrap with keepalive_stage2.sh.

Usage:
    python -u backtest/src/stage2_sizing_risk.py --entry A --trials 120
"""
import argparse
import importlib.util
import os
from pathlib import Path

import optuna

HERE  = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh    = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

DOE_DIR = dh.DOE_DIR

PINNED_ENTRY = {
    "trend_min_confluence":   6,
    "range_min_confluence":   3,
    "min_quality_factors":    3,
    "atr_min_percentile":     41.0,
    "atr_vol_ratio_range":    1.4,
    "use_fib_filter":         False,
    "fib_zone_type":          "golden_only",
    "entry_limit_offset_atr": 0.0,
}

ENTRIES = {
    "A": {"entry_fib_level": 0.55, "entry_fib_level_volatile": 0.80,
          "fib_vol_ratio_threshold": 1.05,
          "use_trend_quality_gate": False, "adx_min_entry": 0.0},
    "B": {"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
          "fib_vol_ratio_threshold": 1.15,
          "use_trend_quality_gate": False, "adx_min_entry": 0.0},
}

# Fixed Stage 1 anchor: with mults=1.0 reproduces Stage 1 results bit-for-bit.
BASE_RISK_PCT = 1.1

# Windows worst-first so breachy trials veto early.
WINDOWS = [
    ("2022-01-01", "2024-12-31"),
    ("2016-01-01", "2018-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2019-07-01", "2022-06-30"),
]

WALL_MARGIN = float(os.getenv("WALL_MARGIN", "8.0"))
MARGIN_K    = float(os.getenv("MARGIN_K", "20000"))


def _suggest(trial) -> dict:
    """Suggest regime-coherent risk + TDD ladder levers."""
    # Regime-coherent risk multipliers (replaces VOL_SIZE)
    calm_mult = trial.suggest_float("RISK_CALM_MULT",    0.50, 1.50, step=0.05)
    vol_mult  = trial.suggest_float("RISK_VOLATILE_MULT", 0.40, 1.80, step=0.05)

    # Drawdown gate: collapse size-up once TDD/DDD reaches this %
    regime_off = trial.suggest_float("VOL_REGIME_DD_OFF", 2.0, 5.0, step=0.5)

    # Cumulative open-risk cap + daily halt
    cum_risk   = trial.suggest_float("CFG_MAX_CUM_RISK", 2.5, 5.0, step=0.5)
    daily_halt = trial.suggest_float("CFG_DAILY_HALT_PCT", 1.5, 3.5, step=0.25)

    # 4-rung TDD ladder: thresholds strictly increasing, risks decreasing
    caut_t = trial.suggest_float("CFG_TDD_CAUTION_PCT",   3.0, 6.0, step=0.5)
    warn_t = trial.suggest_float("CFG_TDD_WARNING_PCT",   caut_t + 0.5, 8.0, step=0.5)
    emer_t = trial.suggest_float("CFG_TDD_EMERGENCY_PCT", warn_t + 0.5, 9.0, step=0.5)
    r_caut  = trial.suggest_float("CFG_RISK_CAUTIOUS",     0.20, 0.80, step=0.05)
    r_cons  = trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.15, min(r_caut, 0.60), step=0.05)
    r_ultra = trial.suggest_float("CFG_RISK_ULTRASAFE",    0.10, min(r_cons, 0.40), step=0.05)
    wall_safety = trial.suggest_float("TDD_WALL_SAFETY",   2.0, 5.0, step=0.5)

    env_over = {
        # Regime-coherent risk ON; ATR-percentile vol-size OFF (different signal)
        "RISK_REGIME_ENABLE":    "1",
        "VOL_SIZE_ENABLE":       "0",
        "RISK_CALM_MULT":        f"{calm_mult}",
        "RISK_VOLATILE_MULT":    f"{vol_mult}",
        "VOL_REGIME_DD_OFF":     f"{regime_off}",
        "VOL_REGIME_DD_MULT":    "1.0",
        "CFG_MAX_CUM_RISK":      f"{cum_risk}",
        "CFG_DAILY_HALT_PCT":    f"{daily_halt}",
        "CFG_TDD_CAUTION_PCT":   f"{caut_t}",
        "CFG_RISK_CAUTIOUS":     f"{r_caut}",
        "CFG_TDD_WARNING_PCT":   f"{warn_t}",
        "CFG_RISK_CONSERVATIVE": f"{r_cons}",
        "CFG_TDD_EMERGENCY_PCT": f"{emer_t}",
        "CFG_RISK_ULTRASAFE":    f"{r_ultra}",
        "TDD_WALL_SAFETY":       f"{wall_safety}",
    }
    return env_over


def make_objective(entry_key: str):
    entry = ENTRIES[entry_key]

    def objective(trial):
        env_over = _suggest(trial)
        tp_over = {**PINNED_ENTRY, **entry, "risk_per_trade_pct": BASE_RISK_PCT}

        nets, worst_tdd = [], 0.0
        for i, (start, end) in enumerate(WINDOWS):
            r = dh.run_single(env_over, tp_over, start, end)
            if r is None:
                trial.set_user_attr("infra_fail_window", i)
                return -3e9
            a = dh.extract_attrs(r)
            if a["failed"]:
                trial.set_user_attr("fail_window", i)
                trial.set_user_attr("n_survived", len(nets))
                return -1e9 + len(nets) * 1e6
            nets.append(a["net"])
            worst_tdd = max(worst_tdd, a.get("max_tdd", 0.0) or 0.0)
            trial.set_user_attr(f"net_w{i}", a["net"])

        maximin = min(nets)
        avg_net = sum(nets) / len(nets)
        pen = MARGIN_K * max(0.0, worst_tdd - WALL_MARGIN) ** 2
        trial.set_user_attr("maximin", maximin)
        trial.set_user_attr("avg_net", round(avg_net))
        trial.set_user_attr("worst_tdd", round(worst_tdd, 2))
        return maximin - pen

    return objective


# Seed with Stage 1 anchor + bracket variants.
# Stage 1 reproduced with calm=1.0, vol=1.0 (mults = identity).
_BASE_SEED = {
    "VOL_REGIME_DD_OFF": 3.0, "CFG_MAX_CUM_RISK": 3.5, "CFG_DAILY_HALT_PCT": 2.5,
    "CFG_TDD_CAUTION_PCT": 5.5, "CFG_RISK_CAUTIOUS": 0.45,
    "CFG_TDD_WARNING_PCT": 7.5, "CFG_RISK_CONSERVATIVE": 0.25,
    "CFG_TDD_EMERGENCY_PCT": 8.5, "CFG_RISK_ULTRASAFE": 0.25, "TDD_WALL_SAFETY": 4.5,
}
SEEDS = [
    {**_BASE_SEED, "RISK_CALM_MULT": 1.00, "RISK_VOLATILE_MULT": 1.00},  # Stage 1 anchor
    {**_BASE_SEED, "RISK_CALM_MULT": 0.80, "RISK_VOLATILE_MULT": 1.20},  # size up volatile
    {**_BASE_SEED, "RISK_CALM_MULT": 1.20, "RISK_VOLATILE_MULT": 0.80},  # size up calm
]


def main():
    ap = argparse.ArgumentParser(description="Stage 2 sizing/risk Optuna optimizer.")
    ap.add_argument("--entry", choices=list(ENTRIES), required=True)
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    study_name = f"stage2_{args.entry}"
    storage = f"sqlite:///{DOE_DIR}/stage2_{args.entry}.db"
    study = optuna.create_study(direction="maximize", study_name=study_name,
                                storage=storage, load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42))

    if not study.trials:
        for s in SEEDS:
            study.enqueue_trial(s)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE,
                              optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[stage2 {args.entry}] entry={ENTRIES[args.entry]}", flush=True)
    print(f"[stage2 {args.entry}] BASE_RISK={BASE_RISK_PCT}%  RISK_REGIME_ENABLE=1  VOL_SIZE retired", flush=True)
    print(f"[stage2 {args.entry}] {done} trials done, running {remaining} more "
          f"(target {args.trials}), jobs={args.jobs}", flush=True)

    if remaining > 0:
        study.optimize(make_objective(args.entry), n_trials=remaining, n_jobs=args.jobs)

    survivors = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE and t.value > -1e8]
    print(f"\n[stage2 {args.entry}] STAGE2 COMPLETE — {len(survivors)} surviving trials")
    if survivors:
        best = study.best_trial
        print(f"  BEST maximin={best.value:,.0f}  avg_net={best.user_attrs.get('avg_net'):,}"
              f"  worst_tdd={best.user_attrs.get('worst_tdd')}%")
        print(f"  params: {best.params}")
    print(f"[stage2 {args.entry}] STAGE2_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
