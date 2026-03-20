#!/usr/bin/env python3
"""
Focused TP + Trailing Stop Optimizer

Only optimizes:
  - TP1-TP5 R-multiples
  - TP1-TP5 close percentages
  - trail_activation_r
  - trail_offset_factor

All other parameters are FROZEN from current_params.json.

Usage:
    python backtest/optimize_tp_trail.py --trials 100 --start 2015-01-01 --end 2015-05-31 --parallel 3
    nohup python backtest/optimize_tp_trail.py --trials 200 --start 2015-01-01 --end 2015-05-31 --parallel 3 > optimize_tp_trail.log 2>&1 &
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
# PARAMETER RANGES - Only TP + Trailing
# ═══════════════════════════════════════════════════════════════════════════════

TP_R_RANGES = {
    'tp1_r_multiple': (0.3, 1.2),
    'tp2_r_multiple': (0.8, 2.6),
    'tp3_r_multiple': (1.2, 3.2),
    'tp4_r_multiple': (1.6, 4.2),
    'tp5_r_multiple': (2.2, 6.0),
}

TP_CLOSE_RANGES = {
    'tp1_close_pct': (0.05, 0.45),
    'tp2_close_pct': (0.10, 0.65),
    'tp3_close_pct': (0.05, 0.45),
    'tp4_close_pct': (0.05, 0.45),
    'tp5_close_pct': (0.05, 0.40),
}

TRAIL_RANGES = {
    'trail_activation_r': (0.5, 3.0),
    'trail_offset_factor': (0.0, 1.0),   # 0=tight at TP, 1=full risk unit buffer
}


def load_frozen_params() -> Dict[str, Any]:
    """Load current params - these stay fixed (except TP + trailing)."""
    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'r') as f:
        data = json.load(f)
    return data.get('parameters', data)


def create_temp_params_file(params: Dict[str, Any]) -> Path:
    """Create a temporary params file for the backtest."""
    temp_dir = Path(tempfile.gettempdir()) / "optimizer_params"
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    full_params = {
        "optimization_mode": "TP_TRAIL_OPTIMIZER",
        "timestamp": datetime.now().isoformat(),
        "parameters": params
    }
    with open(temp_file, 'w') as f:
        json.dump(full_params, f, indent=2)
    return temp_file


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float = 20000):
    """Run backtest with given parameters and return results."""
    temp_params = create_temp_params_file(params)
    output_dir = Path(tempfile.gettempdir()) / "optimizer_results" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
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

        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1800,
            cwd=str(Path(__file__).parent.parent)
        )

        results_file = output_dir / "results.json"
        if results_file.exists():
            with open(results_file, 'r') as f:
                data = json.load(f)
            return {
                'net_return_pct': data.get('return_pct', 0),
                'total_trades': data.get('total_trades', 0),
                'win_rate': data.get('win_rate', 0),
                'max_tdd_pct': data.get('max_tdd_pct', 100),
                'max_ddd_pct': data.get('max_ddd_pct', 100),
                'final_balance': data.get('final_balance', balance),
                'ddd_halts': data.get('ddd_halts', 0),
                'valid': (data.get('max_tdd_pct', 100) < 10 and data.get('max_ddd_pct', 100) < 5),
                'monthly_stats': data.get('monthly_stats', {}),
                'safety_events': data.get('safety_events', data.get('ddd_halts', 0)),
                'tdd_warnings': data.get('tdd_warnings', 0),
            }
        else:
            return None

    except subprocess.TimeoutExpired:
        print(f"  ⚠️ Backtest timed out")
        return None
    except Exception as e:
        print(f"  ⚠️ Backtest error: {e}")
        return None
    finally:
        if temp_params.exists():
            temp_params.unlink()


def objective(trial: optuna.Trial, start: str, end: str, balance: float,
              frozen_params: Dict[str, Any]) -> float:
    """Optuna objective - only sample TP + trailing, freeze everything else."""

    # Start from frozen params
    params = dict(frozen_params)

    # === SAMPLE TP R-MULTIPLES (ordered) ===
    prev_r = 0.3
    for i in range(1, 6):
        key = f'tp{i}_r_multiple'
        low, high = TP_R_RANGES[key]
        low = max(low, prev_r + 0.1)
        r_val = trial.suggest_float(key, low, high, step=0.1)
        params[key] = r_val
        prev_r = r_val

    # === SAMPLE TP CLOSE PERCENTAGES (normalized to 1.0) ===
    weights = []
    for i in range(1, 6):
        key = f'tp{i}_close_pct'
        low, high = TP_CLOSE_RANGES[key]
        w = trial.suggest_float(f'{key}_weight', low, high, step=0.05)
        weights.append(w)
    total = sum(weights)
    for i, w in enumerate(weights, 1):
        params[f'tp{i}_close_pct'] = round(w / total, 3)

    # === SAMPLE TRAILING PARAMETERS ===
    params['trail_activation_r'] = trial.suggest_float(
        'trail_activation_r',
        TRAIL_RANGES['trail_activation_r'][0],
        TRAIL_RANGES['trail_activation_r'][1],
        step=0.1
    )
    params['trail_offset_factor'] = trial.suggest_float(
        'trail_offset_factor',
        TRAIL_RANGES['trail_offset_factor'][0],
        TRAIL_RANGES['trail_offset_factor'][1],
        step=0.05
    )

    # Keep use_atr_trailing always true
    params['use_atr_trailing'] = True

    # === RUN BACKTEST ===
    print(f"\n  Trial {trial.number}: Running backtest...")
    print(f"    TPs: {params['tp1_r_multiple']:.1f}R / {params['tp2_r_multiple']:.1f}R / {params['tp3_r_multiple']:.1f}R / {params['tp4_r_multiple']:.1f}R / {params['tp5_r_multiple']:.1f}R")
    print(f"    Close%: {params['tp1_close_pct']:.0%} / {params['tp2_close_pct']:.0%} / {params['tp3_close_pct']:.0%} / {params['tp4_close_pct']:.0%} / {params['tp5_close_pct']:.0%}")
    print(f"    Trail: activation={params['trail_activation_r']:.1f}R, offset={params['trail_offset_factor']:.2f}")

    result = run_backtest(params, start, end, balance)

    if result is None:
        return -1000

    # Store metrics
    for k, v in result.items():
        if k != 'monthly_stats':
            trial.set_user_attr(k, v)
        else:
            trial.set_user_attr(k, v or {})

    print(f"    → Return: {result['net_return_pct']:+.1f}%, Trades: {result['total_trades']}, Win: {result['win_rate']:.1f}%")
    print(f"    → TDD: {result['max_tdd_pct']:.2f}%, DDD: {result['max_ddd_pct']:.2f}%, Halts: {result['ddd_halts']}, Valid: {result['valid']}")

    # === SCORING ===
    if not result['valid']:
        return -1000 - result['max_ddd_pct'] * 10

    if result['max_ddd_pct'] >= 5.0:
        return -500 - result['max_ddd_pct'] * 20

    if result['total_trades'] < 10:
        return -500 + result['total_trades']

    win_rate_factor = result['win_rate'] / 100.0
    if win_rate_factor >= 0.5:
        wr_multiplier = 0.5 + (win_rate_factor * 1.5)
    else:
        wr_multiplier = win_rate_factor

    trade_bonus = min(result['total_trades'] / 5, 20)

    score = (
        result['net_return_pct'] * wr_multiplier +
        trade_bonus
    )

    if result['max_tdd_pct'] > 5.0:
        score -= (result['max_tdd_pct'] - 5.0) * 15

    if result['ddd_halts'] == 0 and result['max_ddd_pct'] < 2.5:
        score += 10

    return score


def run_optimization(trials: int, start: str, end: str, balance: float = 20000,
                     output_dir: str = 'backtest/optimization_results', n_jobs: int = 1):
    """Run the focused TP + trailing optimization."""

    frozen_params = load_frozen_params()

    print("=" * 70)
    print("FOCUSED TP + TRAILING STOP OPTIMIZER")
    print("=" * 70)
    print(f"  Trials: {trials}")
    print(f"  Period: {start} to {end}")
    print(f"  Balance: ${balance:,.0f}")
    print(f"  Parallel Workers: {n_jobs}")
    print(f"  Optimizing: TP1-5 R-multiples, TP1-5 close%, trail_activation_r, trail_offset_factor")
    print(f"  Frozen: risk={frozen_params.get('risk_per_trade_pct')}, confluence=T{frozen_params.get('trend_min_confluence')}/R{frozen_params.get('range_min_confluence')}/Q{frozen_params.get('min_quality_factors')}, entry_fib={frozen_params.get('entry_fib_level')}")
    print("=" * 70)

    sampler = TPESampler(seed=42)
    study = optuna.create_study(
        direction='maximize',
        sampler=sampler,
        study_name=f"tp_trail_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Seed trial 0 with current params
    enqueue = {}
    for i in range(1, 6):
        key = f'tp{i}_r_multiple'
        if key in frozen_params:
            enqueue[key] = frozen_params[key]
        ckey = f'tp{i}_close_pct'
        wkey = f'{ckey}_weight'
        if ckey in frozen_params:
            enqueue[wkey] = frozen_params[ckey]
    for key in ['trail_activation_r', 'trail_offset_factor']:
        if key in frozen_params:
            enqueue[key] = frozen_params[key]
    if enqueue:
        study.enqueue_trial(enqueue)

    study.optimize(
        lambda trial: objective(trial, start, end, balance, frozen_params),
        n_trials=trials,
        n_jobs=n_jobs,
        show_progress_bar=True,
        catch=(Exception,)
    )

    best = study.best_trial

    print("\n" + "=" * 70)
    print("OPTIMIZATION COMPLETE")
    print("=" * 70)
    print(f"  Best Score: {best.value:.2f}")
    print(f"  Return: {best.user_attrs.get('net_return_pct', 0):+.1f}%")
    print(f"  Trades: {best.user_attrs.get('total_trades', 0)}")
    print(f"  Win Rate: {best.user_attrs.get('win_rate', 0):.1f}%")
    print(f"  Max TDD: {best.user_attrs.get('max_tdd_pct', 0):.2f}%")
    print(f"  Max DDD: {best.user_attrs.get('max_ddd_pct', 0):.2f}%")
    print(f"  Safety Events: {best.user_attrs.get('safety_events', best.user_attrs.get('ddd_halts', 0))}")
    print("=" * 70)

    print("\n📊 BEST PARAMETERS:")
    for key, value in sorted(best.params.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")

    # Monthly breakdown
    monthly = best.user_attrs.get('monthly_stats', {})
    if monthly:
        print("\n📅 MONTHLY BREAKDOWN (Best Trial):")
        print("  " + "-" * 60)
        print(f"  {'Month':<10} {'Trades':>8} {'Winners':>8} {'Win%':>8} {'PnL':>12}")
        print("  " + "-" * 60)
        for month in sorted(monthly.keys()):
            m = monthly[month]
            trades = m.get('trades', 0)
            winners = m.get('winners', 0)
            pnl = m.get('pnl', 0)
            wr = (winners / trades * 100) if trades > 0 else 0
            print(f"  {month:<10} {trades:>8} {winners:>8} {wr:>7.1f}% ${pnl:>10,.0f}")
        print("  " + "-" * 60)

    # All trials summary
    print("\n" + "=" * 70)
    print("ALL TRIALS SUMMARY (top 20)")
    print("=" * 70)
    print(f"{'#':>3} {'Score':>8} {'Return':>8} {'Trades':>7} {'WR%':>6} {'TDD':>6} {'DDD':>6} {'Safe':>5}")
    print("-" * 70)
    for t in sorted(study.trials, key=lambda x: x.value if x.value else -999, reverse=True)[:20]:
        score = t.value if t.value else -999
        ret = t.user_attrs.get('net_return_pct', 0)
        trades = t.user_attrs.get('total_trades', 0)
        wr = t.user_attrs.get('win_rate', 0)
        tdd = t.user_attrs.get('max_tdd_pct', 0)
        ddd = t.user_attrs.get('max_ddd_pct', 0)
        safe = t.user_attrs.get('safety_events', t.user_attrs.get('ddd_halts', 0))
        print(f"{t.number:>3} {score:>8.1f} {ret:>+7.1f}% {trades:>7} {wr:>5.1f}% {tdd:>5.1f}% {ddd:>5.1f}% {safe:>5}")
    print("-" * 70)
    if len(study.trials) > 20:
        print(f"  (Showing top 20 of {len(study.trials)} trials)")

    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build full best params (frozen + optimized)
    best_full_params = dict(frozen_params)
    best_full_params.update(best.params)
    # Normalize weight keys back to close_pct
    for i in range(1, 6):
        wkey = f'tp{i}_close_pct_weight'
        if wkey in best_full_params:
            del best_full_params[wkey]
    # Recalculate close pcts from best trial
    weights = []
    for i in range(1, 6):
        wkey = f'tp{i}_close_pct_weight'
        weights.append(best.params.get(wkey, 0.2))
    total_w = sum(weights)
    for i, w in enumerate(weights, 1):
        best_full_params[f'tp{i}_close_pct'] = round(w / total_w, 3)

    results = {
        "optimization_mode": "TP_TRAIL_FOCUSED",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": trials,
            "start": start,
            "end": end,
            "balance": balance,
            "optimized_params": "TP1-5 R-multiples, TP1-5 close%, trail_activation_r, trail_offset_factor",
            "frozen_params": "All others from current_params.json",
        },
        "best_score": best.value,
        "best_metrics": {
            "net_return_pct": best.user_attrs.get('net_return_pct', 0),
            "total_trades": best.user_attrs.get('total_trades', 0),
            "win_rate": best.user_attrs.get('win_rate', 0),
            "max_tdd_pct": best.user_attrs.get('max_tdd_pct', 0),
            "max_ddd_pct": best.user_attrs.get('max_ddd_pct', 0),
            "valid": best.user_attrs.get('valid', False),
        },
        "best_parameters": best_full_params,
        "best_trial_params_only": best.params,
        "all_trials": [
            {
                "trial": t.number,
                "score": t.value if t.value is not None else -1000,
                "params": t.params,
                "metrics": {k: v for k, v in t.user_attrs.items()},
            }
            for t in study.trials
        ]
    }

    results_file = output_path / f"optimization_tp_trail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to: {results_file}")
    print("\n" + "=" * 70)
    print("To apply best parameters to current_params.json, run:")
    print(f"  python backtest/optimize_tp_trail.py --apply {results_file}")
    print("=" * 70)

    return results


def apply_params(results_file: str):
    """Apply optimized parameters to current_params.json."""
    from params.params_loader import load_params_dict

    with open(results_file, 'r') as f:
        results = json.load(f)

    best_params = results.get('best_parameters', {})

    current = load_params_dict()
    if 'parameters' in current:
        current['parameters'].update(best_params)
    else:
        current.update(best_params)

    current['optimization_mode'] = "TP_TRAIL_FOCUSED"
    current['timestamp'] = datetime.now().isoformat()
    current['best_score'] = results.get('best_score', 0)
    current['optimization_period'] = f"{results['config']['start']} to {results['config']['end']}"
    current['source'] = f"TP+Trail Optimizer - Score {results.get('best_score', 0):.1f}"

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    print(f"✅ Applied best parameters to {params_file}")
    print("\nApplied parameters:")
    for key, value in sorted(best_params.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Focused TP + Trailing Stop Optimizer')
    parser.add_argument('--trials', type=int, default=100, help='Number of optimization trials')
    parser.add_argument('--start', type=str, default='2015-01-01', help='Backtest start date')
    parser.add_argument('--end', type=str, default='2015-05-31', help='Backtest end date')
    parser.add_argument('--balance', type=float, default=20000, help='Initial balance')
    parser.add_argument('--output', type=str, default='backtest/optimization_results', help='Output directory')
    parser.add_argument('--apply', type=str, help='Apply parameters from results file')
    parser.add_argument('--parallel', '-j', type=int, default=1, help='Number of parallel workers')

    args = parser.parse_args()

    if args.apply:
        apply_params(args.apply)
    else:
        run_optimization(
            trials=args.trials,
            start=args.start,
            end=args.end,
            balance=args.balance,
            output_dir=args.output,
            n_jobs=args.parallel
        )
