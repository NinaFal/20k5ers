#!/usr/bin/env python3
"""
Entry-Only Optimizer — Same signals, better entry prices.

Optimizes ONLY entry_fib_level and entry_limit_offset_atr while keeping
all other parameters fixed at their current values.

Usage:
    python backtest/optimize_entry.py --trials 50 --start 2024-01-01 --end 2024-12-31
    python backtest/optimize_entry.py --trials 100 --start 2023-01-01 --end 2025-12-31 -j 4
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

# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY REFINEMENT RANGES
# ═══════════════════════════════════════════════════════════════════════════════
ENTRY_FIB_RANGE = (0.5, 0.786)           # 0.5=shallow, 0.786=deep retracement
ENTRY_OFFSET_ATR_RANGE = (0.0, 0.5)      # 0=no offset, 0.5=aggressive ATR offset


@dataclass
class Result:
    params: Dict[str, Any]
    net_return_pct: float = -100
    total_trades: int = 0
    win_rate: float = 0
    max_tdd_pct: float = 100
    max_ddd_pct: float = 100
    final_balance: float = 0
    ddd_halts: int = 0
    valid: bool = False


def load_base_params() -> Dict[str, Any]:
    """Load current params as the fixed base."""
    from params.params_loader import load_params_dict
    data = load_params_dict()
    return data.get('parameters', data)


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float) -> Result:
    """Run backtest — NO timeout for maximum speed."""
    temp_dir = Path(tempfile.gettempdir()) / "entry_optimizer"
    temp_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    temp_file = temp_dir / f"params_{stamp}.json"
    output_dir = temp_dir / f"run_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(temp_file, 'w') as f:
        json.dump({
            "optimization_mode": "ENTRY_OPTIMIZER",
            "timestamp": datetime.now().isoformat(),
            "parameters": params,
        }, f, indent=2)

    try:
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "src" / "main_live_bot_backtest.py"),
            "--start", start,
            "--end", end,
            "--balance", str(balance),
            "--output", str(output_dir),
            "--params-file", str(temp_file),
            "--quiet",
        ]

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).parent.parent),
        )

        results_file = output_dir / "results.json"
        if results_file.exists():
            with open(results_file) as f:
                data = json.load(f)
            return Result(
                params=params,
                net_return_pct=data.get('return_pct', 0),
                total_trades=data.get('total_trades', 0),
                win_rate=data.get('win_rate', 0),
                max_tdd_pct=data.get('max_tdd_pct', 100),
                max_ddd_pct=data.get('max_ddd_pct', 100),
                final_balance=data.get('final_balance', balance),
                ddd_halts=data.get('ddd_halts', 0),
                valid=(data.get('max_tdd_pct', 100) < 10 and data.get('max_ddd_pct', 100) < 5),
            )
    except Exception as e:
        print(f"  Backtest error: {e}")
    finally:
        if temp_file.exists():
            temp_file.unlink()

    return Result(params=params)


def objective(trial: optuna.Trial, base_params: Dict[str, Any],
              start: str, end: str, balance: float) -> float:
    """Optimize ONLY entry parameters. Everything else is fixed."""
    params = base_params.copy()

    params['entry_fib_level'] = trial.suggest_float(
        'entry_fib_level', ENTRY_FIB_RANGE[0], ENTRY_FIB_RANGE[1], step=0.01
    )
    params['entry_limit_offset_atr'] = trial.suggest_float(
        'entry_limit_offset_atr', ENTRY_OFFSET_ATR_RANGE[0], ENTRY_OFFSET_ATR_RANGE[1], step=0.02
    )

    fib = params['entry_fib_level']
    offset = params['entry_limit_offset_atr']
    print(f"\n  Trial {trial.number}: fib={fib:.3f}, offset={offset:.2f}×ATR")

    result = run_backtest(params, start, end, balance)

    trial.set_user_attr('net_return_pct', result.net_return_pct)
    trial.set_user_attr('total_trades', result.total_trades)
    trial.set_user_attr('win_rate', result.win_rate)
    trial.set_user_attr('max_tdd_pct', result.max_tdd_pct)
    trial.set_user_attr('max_ddd_pct', result.max_ddd_pct)
    trial.set_user_attr('ddd_halts', result.ddd_halts)
    trial.set_user_attr('valid', result.valid)

    print(f"    -> Return: {result.net_return_pct:+.1f}%, Trades: {result.total_trades}, "
          f"Win: {result.win_rate:.1f}%, TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%")

    # === SCORING (same as main optimizer) ===
    if not result.valid:
        return -1000 - result.max_ddd_pct * 10
    if result.max_ddd_pct >= 5.0:
        return -500 - result.max_ddd_pct * 20
    if result.total_trades < 10:
        return -500 + result.total_trades

    wr = result.win_rate / 100.0
    wr_mult = 0.5 + (wr * 1.5) if wr >= 0.5 else wr
    trade_bonus = min(result.total_trades / 5, 20)

    score = result.net_return_pct * wr_mult + trade_bonus
    if result.max_tdd_pct > 5.0:
        score -= (result.max_tdd_pct - 5.0) * 15
    if result.ddd_halts == 0 and result.max_ddd_pct < 2.5:
        score += 10

    return score


def main():
    parser = argparse.ArgumentParser(description='Entry-Only Optimizer')
    parser.add_argument('--trials', type=int, default=50)
    parser.add_argument('--start', type=str, default='2024-01-01')
    parser.add_argument('--end', type=str, default='2024-12-31')
    parser.add_argument('--balance', type=float, default=20000)
    parser.add_argument('--parallel', '-j', type=int, default=1)
    parser.add_argument('--apply', type=str, help='Apply results file to current_params.json')
    args = parser.parse_args()

    if args.apply:
        apply_params(args.apply)
        return

    base_params = load_base_params()

    print("=" * 70)
    print("ENTRY-ONLY OPTIMIZER")
    print("=" * 70)
    print(f"  Trials:  {args.trials}")
    print(f"  Period:  {args.start} to {args.end}")
    print(f"  Balance: ${args.balance:,.0f}")
    print(f"  Workers: {args.parallel}")
    print(f"  Fib range:    {ENTRY_FIB_RANGE[0]} - {ENTRY_FIB_RANGE[1]}")
    print(f"  Offset range: {ENTRY_OFFSET_ATR_RANGE[0]} - {ENTRY_OFFSET_ATR_RANGE[1]} ATR")
    print(f"  Baseline:     fib={base_params.get('entry_fib_level', 0.618):.3f}, "
          f"offset={base_params.get('entry_limit_offset_atr', 0.0):.2f}")
    print("  ALL other params: FIXED at current values")
    print("=" * 70)

    study = optuna.create_study(
        direction='maximize',
        sampler=TPESampler(seed=42),
        study_name=f"entry_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    # Seed trial 0 with current baseline (fib=0.618, offset=0.0)
    study.enqueue_trial({
        'entry_fib_level': base_params.get('entry_fib_level', 0.618),
        'entry_limit_offset_atr': base_params.get('entry_limit_offset_atr', 0.0),
    })

    study.optimize(
        lambda trial: objective(trial, base_params, args.start, args.end, args.balance),
        n_trials=args.trials,
        n_jobs=args.parallel,
        show_progress_bar=True,
        catch=(Exception,),
    )

    best = study.best_trial

    print("\n" + "=" * 70)
    print("ENTRY OPTIMIZATION COMPLETE")
    print("=" * 70)
    print(f"  Best Score:  {best.value:.2f}")
    print(f"  Fib Level:   {best.params['entry_fib_level']:.3f}")
    print(f"  ATR Offset:  {best.params['entry_limit_offset_atr']:.2f}")
    print(f"  Return:      {best.user_attrs.get('net_return_pct', 0):+.1f}%")
    print(f"  Trades:      {best.user_attrs.get('total_trades', 0)}")
    print(f"  Win Rate:    {best.user_attrs.get('win_rate', 0):.1f}%")
    print(f"  Max TDD:     {best.user_attrs.get('max_tdd_pct', 0):.2f}%")
    print(f"  Max DDD:     {best.user_attrs.get('max_ddd_pct', 0):.2f}%")
    print("=" * 70)

    # Baseline comparison
    baseline = study.trials[0] if study.trials else None
    if baseline and baseline.number == 0:
        b_ret = baseline.user_attrs.get('net_return_pct', 0)
        b_wr = baseline.user_attrs.get('win_rate', 0)
        best_ret = best.user_attrs.get('net_return_pct', 0)
        best_wr = best.user_attrs.get('win_rate', 0)
        print(f"\n  BASELINE (0.618/0.0):  {b_ret:+.1f}% return, {b_wr:.1f}% WR")
        print(f"  BEST ENTRY:            {best_ret:+.1f}% return, {best_wr:.1f}% WR")
        print(f"  IMPROVEMENT:           {best_ret - b_ret:+.1f}% return")

    # All trials table
    print("\n" + "=" * 70)
    print("ALL TRIALS")
    print("=" * 70)
    print(f"{'#':>3} {'Score':>8} {'Fib':>6} {'Offset':>7} {'Return':>8} {'Trades':>7} {'WR%':>6} {'TDD':>6} {'DDD':>6}")
    print("-" * 70)
    for t in sorted(study.trials, key=lambda x: x.value if x.value else -999, reverse=True):
        s = t.value if t.value else -999
        fib = t.params.get('entry_fib_level', 0)
        off = t.params.get('entry_limit_offset_atr', 0)
        ret = t.user_attrs.get('net_return_pct', 0)
        trades = t.user_attrs.get('total_trades', 0)
        wr = t.user_attrs.get('win_rate', 0)
        tdd = t.user_attrs.get('max_tdd_pct', 0)
        ddd = t.user_attrs.get('max_ddd_pct', 0)
        marker = " <-- baseline" if t.number == 0 else ""
        print(f"{t.number:>3} {s:>8.1f} {fib:>6.3f} {off:>6.2f}x {ret:>+7.1f}% {trades:>7} {wr:>5.1f}% {tdd:>5.1f}% {ddd:>5.1f}%{marker}")
    print("-" * 70)

    # Save results
    output_dir = Path('backtest/optimization_results')
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "optimization_mode": "ENTRY_ONLY",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": args.trials,
            "start": args.start,
            "end": args.end,
            "balance": args.balance,
            "fib_range": list(ENTRY_FIB_RANGE),
            "offset_range": list(ENTRY_OFFSET_ATR_RANGE),
        },
        "best_score": best.value,
        "best_parameters": best.params,
        "best_metrics": {k: v for k, v in best.user_attrs.items()},
        "all_trials": [
            {
                "trial": t.number,
                "score": t.value if t.value is not None else -1000,
                "params": t.params,
                "metrics": {k: v for k, v in t.user_attrs.items()},
            }
            for t in study.trials
        ],
    }

    results_file = output_dir / f"entry_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {results_file}")
    print(f"\nTo apply: python backtest/optimize_entry.py --apply {results_file}")


def apply_params(results_file: str):
    """Apply best entry params to current_params.json."""
    from params.params_loader import load_params_dict

    with open(results_file) as f:
        results = json.load(f)

    best = results.get('best_parameters', {})

    current = load_params_dict()
    target = current.get('parameters', current)
    target['entry_fib_level'] = best['entry_fib_level']
    target['entry_limit_offset_atr'] = best['entry_limit_offset_atr']
    current['timestamp'] = datetime.now().isoformat()

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    print(f"Applied to {params_file}:")
    print(f"  entry_fib_level:        {best['entry_fib_level']:.3f}")
    print(f"  entry_limit_offset_atr: {best['entry_limit_offset_atr']:.2f}")


if __name__ == "__main__":
    main()
