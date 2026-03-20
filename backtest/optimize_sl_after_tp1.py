#!/usr/bin/env python3
"""
Optimizer for sl_after_tp1_r ONLY

Optimizes ONLY:
- sl_after_tp1_r: SL position after TP1 hit, between -1R (original SL) and 0.2R (profit lock)

ALL other params are fixed from current_params.json.

Usage:
    python backtest/optimize_sl_after_tp1.py --trials 50 --start 2015-01-01 --end 2015-05-31
    python backtest/optimize_sl_after_tp1.py --apply backtest/optimization_results/sl_tp1_<timestamp>.json
"""

import sys
import os
import json
import argparse
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import optuna
    from optuna.samplers import TPESampler
except ImportError:
    print("ERROR: optuna not installed. Run: pip install optuna")
    sys.exit(1)

optuna.logging.set_verbosity(optuna.logging.WARNING)


# ─── Parameter range ─────────────────────────────────────────────────────────
SL_AFTER_TP1_RANGE = (-1.0, 0.2)   # -1R = original SL, 0 = breakeven, 0.2R = profit lock
SL_STEP = 0.05


@dataclass
class BacktestResult:
    params: Dict[str, Any]
    net_return_pct: float
    total_trades: int
    win_rate: float
    max_tdd_pct: float
    max_ddd_pct: float
    final_balance: float
    ddd_halts: int
    valid: bool
    monthly_stats: Dict[str, Any] = None
    safety_events: int = 0
    tdd_warnings: int = 0


def load_current_params() -> Dict[str, Any]:
    from params.params_loader import load_params_dict
    raw = load_params_dict()
    return raw.get('parameters', raw)


def create_temp_params_file(params: Dict[str, Any]) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "optimizer_sl_tp1_params"
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    full_params = {
        "optimization_mode": "OPTIMIZER_SL_TP1",
        "timestamp": datetime.now().isoformat(),
        "parameters": params,
    }
    with open(temp_file, 'w') as f:
        json.dump(full_params, f, indent=2)
    return temp_file


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float = 20000) -> BacktestResult:
    temp_params = create_temp_params_file(params)
    output_dir = Path(tempfile.gettempdir()) / "optimizer_sl_tp1_results" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "src" / "main_live_bot_backtest.py"),
            "--start", start,
            "--end", end,
            "--balance", str(balance),
            "--output", str(output_dir),
            "--params-file", str(temp_params),
            "--quiet",
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       cwd=str(Path(__file__).parent.parent))

        results_file = output_dir / "results.json"
        if results_file.exists():
            with open(results_file, 'r') as f:
                data = json.load(f)
            return BacktestResult(
                params=params,
                net_return_pct=data.get('return_pct', 0),
                total_trades=data.get('total_trades', 0),
                win_rate=data.get('win_rate', 0),
                max_tdd_pct=data.get('max_tdd_pct', 100),
                max_ddd_pct=data.get('max_ddd_pct', 100),
                final_balance=data.get('final_balance', balance),
                ddd_halts=data.get('ddd_halts', 0),
                valid=(data.get('max_tdd_pct', 100) < 10 and data.get('max_ddd_pct', 100) < 5),
                monthly_stats=data.get('monthly_stats', {}),
                safety_events=data.get('safety_events', data.get('ddd_halts', 0)),
                tdd_warnings=data.get('tdd_warnings', 0),
            )
    except Exception as e:
        print(f"  ⚠️ Backtest error: {e}")
    finally:
        if temp_params.exists():
            temp_params.unlink()

    return BacktestResult(params=params, net_return_pct=-100, total_trades=0, win_rate=0,
                          max_tdd_pct=100, max_ddd_pct=100, final_balance=balance, ddd_halts=0, valid=False)


def objective(trial: optuna.Trial, start: str, end: str, balance: float, base_params: Dict[str, Any]) -> float:
    sl_after_tp1_r = trial.suggest_float('sl_after_tp1_r', SL_AFTER_TP1_RANGE[0], SL_AFTER_TP1_RANGE[1], step=SL_STEP)

    params = dict(base_params)
    params['sl_after_tp1_r'] = sl_after_tp1_r

    print(f"\n  Trial {trial.number}: sl_after_tp1_r = {sl_after_tp1_r:+.2f}R", flush=True)

    result = run_backtest(params, start, end, balance)

    trial.set_user_attr('net_return_pct', result.net_return_pct)
    trial.set_user_attr('total_trades', result.total_trades)
    trial.set_user_attr('win_rate', result.win_rate)
    trial.set_user_attr('max_tdd_pct', result.max_tdd_pct)
    trial.set_user_attr('max_ddd_pct', result.max_ddd_pct)
    trial.set_user_attr('ddd_halts', result.ddd_halts)
    trial.set_user_attr('final_balance', result.final_balance)
    trial.set_user_attr('monthly_stats', result.monthly_stats or {})
    trial.set_user_attr('safety_events', result.safety_events)
    trial.set_user_attr('valid', result.valid)

    print(f"    → Return: {result.net_return_pct:+.1f}%, Trades: {result.total_trades}, Win: {result.win_rate:.1f}%")
    print(f"    → TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%, DDD Halts: {result.ddd_halts}, Valid: {result.valid}")

    # Scoring (same logic as main optimizer)
    if not result.valid:
        return -1000 - result.max_ddd_pct * 10

    if result.max_ddd_pct >= 5.0:
        return -500 - result.max_ddd_pct * 20

    if result.total_trades < 10:
        return -500 + result.total_trades

    win_rate_factor = result.win_rate / 100.0
    wr_multiplier = 0.5 + (win_rate_factor * 1.5) if win_rate_factor >= 0.5 else win_rate_factor
    trade_bonus = min(result.total_trades / 5, 20)

    score = result.net_return_pct * wr_multiplier + trade_bonus

    if result.max_tdd_pct > 5.0:
        score -= (result.max_tdd_pct - 5.0) * 15

    if result.ddd_halts == 0 and result.max_ddd_pct < 2.5:
        score += 10

    return score


def run_optimization(trials: int, start: str, end: str, balance: float = 20000,
                     output_dir: str = 'backtest/optimization_results') -> Dict[str, Any]:
    base_params = load_current_params()

    print("=" * 70)
    print("SL AFTER TP1 OPTIMIZER")
    print("=" * 70)
    print(f"  Trials:   {trials}")
    print(f"  Period:   {start} to {end}")
    print(f"  Balance:  ${balance:,.0f}")
    print(f"  Range:    sl_after_tp1_r from {SL_AFTER_TP1_RANGE[0]:+.2f}R to {SL_AFTER_TP1_RANGE[1]:+.2f}R (step {SL_STEP})")
    print(f"  Baseline: sl_after_tp1_r = {base_params.get('sl_after_tp1_r', 0.0):+.2f}R")
    print("  Fixed:    all other parameters from current_params.json")
    print("=" * 70)

    # Use grid sampler to exhaustively try all steps in the range
    n_steps = int((SL_AFTER_TP1_RANGE[1] - SL_AFTER_TP1_RANGE[0]) / SL_STEP) + 1
    print(f"  Grid points: {n_steps} (exhaustive grid search)")
    print("=" * 70)

    sampler = TPESampler(seed=42, n_startup_trials=max(5, n_steps))

    study = optuna.create_study(
        direction='maximize',
        sampler=sampler,
        study_name=f"sl_after_tp1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Seed with current value first
    study.enqueue_trial({'sl_after_tp1_r': base_params.get('sl_after_tp1_r', 0.0)})

    study.optimize(
        lambda trial: objective(trial, start, end, balance, base_params),
        n_trials=trials,
        show_progress_bar=False,
        catch=(Exception,)
    )

    best = study.best_trial

    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print(f"  Best sl_after_tp1_r: {best.params['sl_after_tp1_r']:+.2f}R")
    print(f"  Best Score:  {best.value:.2f}")
    print(f"  Return:      {best.user_attrs.get('net_return_pct', 0):+.1f}%")
    print(f"  Trades:      {best.user_attrs.get('total_trades', 0)}")
    print(f"  Win Rate:    {best.user_attrs.get('win_rate', 0):.1f}%")
    print(f"  Max TDD:     {best.user_attrs.get('max_tdd_pct', 0):.2f}%")
    print(f"  Max DDD:     {best.user_attrs.get('max_ddd_pct', 0):.2f}%")
    print(f"  DDD Halts:   {best.user_attrs.get('ddd_halts', 0)}")
    print("=" * 70)

    # Monthly breakdown
    monthly = best.user_attrs.get('monthly_stats', {})
    if monthly:
        print("\n  MONTHLY BREAKDOWN (Best Trial):")
        print("  " + "-" * 55)
        print(f"  {'Month':<10} {'Trades':>8} {'Winners':>8} {'Win%':>7} {'PnL':>12}")
        print("  " + "-" * 55)
        for month in sorted(monthly.keys()):
            m = monthly[month]
            trades = m.get('trades', 0)
            winners = m.get('winners', 0)
            pnl = m.get('pnl', 0)
            wr = (winners / trades * 100) if trades > 0 else 0
            print(f"  {month:<10} {trades:>8} {winners:>8} {wr:>6.1f}% ${pnl:>10,.0f}")
        print("  " + "-" * 55)

    # All trials sorted by sl value
    print("\n  ALL TRIALS (sorted by sl_after_tp1_r):")
    print(f"  {'sl_tp1':>8} {'Score':>8} {'Return':>8} {'Trades':>7} {'WR%':>6} {'TDD':>6} {'DDD':>6}")
    print("  " + "-" * 60)
    for t in sorted(study.trials, key=lambda x: x.params.get('sl_after_tp1_r', -99)):
        score = t.value if t.value is not None else -999
        sl = t.params.get('sl_after_tp1_r', 0)
        ret = t.user_attrs.get('net_return_pct', 0)
        trades = t.user_attrs.get('total_trades', 0)
        wr = t.user_attrs.get('win_rate', 0)
        tdd = t.user_attrs.get('max_tdd_pct', 0)
        ddd = t.user_attrs.get('max_ddd_pct', 0)
        marker = " ← BEST" if t.number == best.number else ""
        print(f"  {sl:>+7.2f}R {score:>8.1f} {ret:>+7.1f}% {trades:>7} {wr:>5.1f}% {tdd:>5.2f}% {ddd:>5.2f}%{marker}")
    print("  " + "-" * 60)

    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    results = {
        "optimization_scope": "SL_AFTER_TP1_ONLY",
        "timestamp": datetime.now().isoformat(),
        "config": {"trials": trials, "start": start, "end": end, "balance": balance,
                   "sl_range": list(SL_AFTER_TP1_RANGE), "sl_step": SL_STEP},
        "best_score": best.value,
        "best_sl_after_tp1_r": best.params['sl_after_tp1_r'],
        "best_metrics": {
            "net_return_pct": best.user_attrs.get('net_return_pct', 0),
            "total_trades": best.user_attrs.get('total_trades', 0),
            "win_rate": best.user_attrs.get('win_rate', 0),
            "max_tdd_pct": best.user_attrs.get('max_tdd_pct', 0),
            "max_ddd_pct": best.user_attrs.get('max_ddd_pct', 0),
            "valid": best.user_attrs.get('valid', False),
        },
        "all_trials": [
            {"trial": t.number, "sl_after_tp1_r": t.params.get('sl_after_tp1_r'),
             "score": t.value if t.value is not None else -1000,
             "metrics": {k: v for k, v in t.user_attrs.items() if k != 'monthly_stats'}}
            for t in sorted(study.trials, key=lambda x: x.params.get('sl_after_tp1_r', -99))
        ]
    }

    results_file = output_path / f"sl_tp1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to: {results_file}")
    print("\nTo apply best value to current_params.json:")
    print(f"  python backtest/optimize_sl_after_tp1.py --apply {results_file}")

    return results


def apply_params(results_file: str):
    from params.params_loader import load_params_dict

    with open(results_file, 'r') as f:
        results = json.load(f)

    best_sl = results['best_sl_after_tp1_r']
    current = load_params_dict()
    params = current.get('parameters', current)
    params['sl_after_tp1_r'] = best_sl
    current['optimization_mode'] = "OPTIMIZER_SL_TP1"
    current['timestamp'] = datetime.now().isoformat()
    current['best_score'] = results.get('best_score', 0)

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    print(f"✅ Applied sl_after_tp1_r = {best_sl:+.2f}R to {params_file}")


def main():
    parser = argparse.ArgumentParser(description='Optimize sl_after_tp1_r parameter only')
    parser.add_argument('--trials', type=int, default=30, help='Number of optimization trials')
    parser.add_argument('--start', type=str, default='2015-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2015-05-31', help='End date (YYYY-MM-DD)')
    parser.add_argument('--balance', type=float, default=20000, help='Starting balance')
    parser.add_argument('--output', type=str, default='backtest/optimization_results', help='Output directory')
    parser.add_argument('--apply', type=str, default=None, help='Apply results from this file')
    args = parser.parse_args()

    if args.apply:
        apply_params(args.apply)
        return

    run_optimization(
        trials=args.trials,
        start=args.start,
        end=args.end,
        balance=args.balance,
        output_dir=args.output,
    )


if __name__ == '__main__':
    main()
