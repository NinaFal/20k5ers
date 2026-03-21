#!/usr/bin/env python3
"""
Friday Safety Parameter Optimizer

Optimizes the Friday position closing parameters via backtest:
- friday_safety_max_per_group        (int 1-4):   Max positions per correlation group
- friday_safety_max_total_non_crypto (int 1-8):   Max total non-crypto positions held over weekend
- friday_safety_r_close_losing       (float):     Close positions below this R-multiple (default 0.0)
- friday_safety_r_new_position       (float):     Reduce 50% positions below this R, hold above (default 0.5)
- friday_safety_r_take_profit        (float):     Close positions above this R-multiple (default 1.6)

The optimizer writes these params into a temp params file and runs the full
main_live_bot_backtest.py for each trial to measure impact on overall performance
and safety. Best params can be applied back to current_params.json.

Usage:
    python backtest/optimize_friday_safety.py --trials 50 --start 2024-01-01 --end 2024-12-31
    python backtest/optimize_friday_safety.py --trials 100 --start 2023-01-01 --end 2025-12-31 --parallel 4
    python backtest/optimize_friday_safety.py --apply backtest/optimization_results/friday_safety_YYYYMMDD.json
"""

import sys
import os
import json
import argparse
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import optuna
    from optuna.samplers import TPESampler
except ImportError:
    print("ERROR: optuna not installed. Run: pip install optuna")
    sys.exit(1)

optuna.logging.set_verbosity(optuna.logging.WARNING)


# ═══════════════════════════════════════════════════════════════════════════════
# FRIDAY SAFETY PARAMETER RANGES
# ═══════════════════════════════════════════════════════════════════════════════

FRIDAY_SAFETY_RANGES = {
    # How many positions per correlation group to keep over the weekend
    'friday_safety_max_per_group': (1, 4),          # Baseline: 2

    # How many total non-crypto positions to keep over the weekend
    'friday_safety_max_total_non_crypto': (1, 8),   # Baseline: 5

    # Close positions with R below this threshold (protect capital)
    'friday_safety_r_close_losing': (-0.5, 0.2),    # Baseline: 0.0

    # Reduce 50% positions below this R, hold above (sweet spot lower bound)
    'friday_safety_r_new_position': (0.1, 1.0),     # Baseline: 0.5

    # Take profit / close above this R (sweet spot upper bound)
    'friday_safety_r_take_profit': (0.8, 3.0),      # Baseline: 1.6
}

# Baseline values (seeded as trial 0)
FRIDAY_SAFETY_BASELINE = {
    'friday_safety_max_per_group': 2,
    'friday_safety_max_total_non_crypto': 5,
    'friday_safety_r_close_losing': 0.0,
    'friday_safety_r_new_position': 0.5,
    'friday_safety_r_take_profit': 1.6,
}


@dataclass
class OptimizationResult:
    """Result of a single backtest run."""
    params: Dict[str, Any]
    net_return_pct: float
    total_trades: int
    win_rate: float
    max_tdd_pct: float
    max_ddd_pct: float
    final_balance: float
    ddd_halts: int
    safety_events: int
    valid: bool
    monthly_stats: Dict[str, Any] = None


def load_base_params() -> Dict[str, Any]:
    """Load non-friday-safety params from current_params.json."""
    from params.params_loader import load_params_dict
    raw = load_params_dict()
    return raw.get('parameters', raw)


def create_temp_params_file(base_params: Dict[str, Any], friday_params: Dict[str, Any]) -> Path:
    """Create a temporary params file merging base params with friday safety overrides."""
    temp_dir = Path(tempfile.gettempdir()) / "friday_optimizer_params"
    temp_dir.mkdir(exist_ok=True)

    merged = dict(base_params)
    merged.update(friday_params)

    temp_file = temp_dir / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    full_params = {
        "optimization_mode": "FRIDAY_SAFETY_OPTIMIZER",
        "timestamp": datetime.now().isoformat(),
        "parameters": merged
    }
    with open(temp_file, 'w') as f:
        json.dump(full_params, f, indent=2)

    return temp_file


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float = 20000) -> OptimizationResult:
    """Run backtest with given parameters and return results."""
    base_params = load_base_params()
    friday_params = {k: v for k, v in params.items() if k.startswith('friday_safety_')}
    temp_params = create_temp_params_file(base_params, friday_params)

    output_dir = (Path(tempfile.gettempdir()) / "friday_optimizer_results" /
                  f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import subprocess
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

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).parent.parent),
        )

        results_file = output_dir / "results.json"
        if results_file.exists():
            with open(results_file, 'r') as f:
                data = json.load(f)
            return OptimizationResult(
                params=params,
                net_return_pct=data.get('return_pct', 0),
                total_trades=data.get('total_trades', 0),
                win_rate=data.get('win_rate', 0),
                max_tdd_pct=data.get('max_tdd_pct', 100),
                max_ddd_pct=data.get('max_ddd_pct', 100),
                final_balance=data.get('final_balance', balance),
                ddd_halts=data.get('ddd_halts', 0),
                safety_events=data.get('safety_events', data.get('ddd_halts', 0)),
                valid=(data.get('max_tdd_pct', 100) < 10 and data.get('max_ddd_pct', 100) < 5),
                monthly_stats=data.get('monthly_stats', {}),
            )

    except Exception as e:
        print(f"  ⚠️ Backtest error: {e}")

    finally:
        if temp_params.exists():
            temp_params.unlink()

    return OptimizationResult(
        params=params, net_return_pct=-100, total_trades=0, win_rate=0,
        max_tdd_pct=100, max_ddd_pct=100, final_balance=balance,
        ddd_halts=0, safety_events=0, valid=False,
    )


def sample_friday_safety_params(trial: optuna.Trial) -> Dict[str, Any]:
    """Sample friday safety parameters for an Optuna trial."""
    params = {}

    params['friday_safety_max_per_group'] = trial.suggest_int(
        'friday_safety_max_per_group',
        FRIDAY_SAFETY_RANGES['friday_safety_max_per_group'][0],
        FRIDAY_SAFETY_RANGES['friday_safety_max_per_group'][1],
    )
    params['friday_safety_max_total_non_crypto'] = trial.suggest_int(
        'friday_safety_max_total_non_crypto',
        FRIDAY_SAFETY_RANGES['friday_safety_max_total_non_crypto'][0],
        FRIDAY_SAFETY_RANGES['friday_safety_max_total_non_crypto'][1],
    )
    params['friday_safety_r_close_losing'] = trial.suggest_float(
        'friday_safety_r_close_losing',
        FRIDAY_SAFETY_RANGES['friday_safety_r_close_losing'][0],
        FRIDAY_SAFETY_RANGES['friday_safety_r_close_losing'][1],
        step=0.05,
    )

    # r_new_position must be > r_close_losing
    r_close_losing = params['friday_safety_r_close_losing']
    r_new_pos_low = max(FRIDAY_SAFETY_RANGES['friday_safety_r_new_position'][0],
                        r_close_losing + 0.1)
    r_new_pos_high = FRIDAY_SAFETY_RANGES['friday_safety_r_new_position'][1]
    if r_new_pos_high < r_new_pos_low + 0.1:
        r_new_pos_high = r_new_pos_low + 0.1
    params['friday_safety_r_new_position'] = trial.suggest_float(
        'friday_safety_r_new_position', r_new_pos_low, r_new_pos_high, step=0.05,
    )

    # r_take_profit must be > r_new_position
    r_new_position = params['friday_safety_r_new_position']
    r_tp_low = max(FRIDAY_SAFETY_RANGES['friday_safety_r_take_profit'][0],
                   r_new_position + 0.2)
    r_tp_high = FRIDAY_SAFETY_RANGES['friday_safety_r_take_profit'][1]
    if r_tp_high < r_tp_low + 0.1:
        r_tp_high = r_tp_low + 0.1
    params['friday_safety_r_take_profit'] = trial.suggest_float(
        'friday_safety_r_take_profit', r_tp_low, r_tp_high, step=0.1,
    )

    return params


def objective(trial: optuna.Trial, start: str, end: str, balance: float) -> float:
    """
    Optuna objective function - maximize a composite score that rewards
    high returns and penalizes safety events / drawdown breaches.
    """
    params = sample_friday_safety_params(trial)

    print(f"\n  Trial {trial.number}: Running backtest...")
    print(f"    max_per_group={params['friday_safety_max_per_group']}, "
          f"max_total_non_crypto={params['friday_safety_max_total_non_crypto']}")
    print(f"    r_close_losing={params['friday_safety_r_close_losing']:.2f}R, "
          f"r_new_position={params['friday_safety_r_new_position']:.2f}R, "
          f"r_take_profit={params['friday_safety_r_take_profit']:.2f}R")

    result = run_backtest(params, start, end, balance)

    # Store result metrics
    trial.set_user_attr('net_return_pct', result.net_return_pct)
    trial.set_user_attr('total_trades', result.total_trades)
    trial.set_user_attr('win_rate', result.win_rate)
    trial.set_user_attr('max_tdd_pct', result.max_tdd_pct)
    trial.set_user_attr('max_ddd_pct', result.max_ddd_pct)
    trial.set_user_attr('ddd_halts', result.ddd_halts)
    trial.set_user_attr('safety_events', result.safety_events)
    trial.set_user_attr('final_balance', result.final_balance)
    trial.set_user_attr('monthly_stats', result.monthly_stats or {})
    trial.set_user_attr('valid', result.valid)

    print(f"    → Return: {result.net_return_pct:+.1f}%, Trades: {result.total_trades}, "
          f"Win: {result.win_rate:.1f}%")
    print(f"    → TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%, "
          f"Safety events: {result.safety_events}, Valid: {result.valid}")

    # ── Scoring ─────────────────────────────────────────────────────────────
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

    # Penalize excessive TDD
    if result.max_tdd_pct > 5.0:
        score -= (result.max_tdd_pct - 5.0) * 15

    # Bonus for clean runs (no DDD halts, low DDD)
    if result.ddd_halts == 0 and result.max_ddd_pct < 2.5:
        score += 10

    # Penalize safety events (DDD stops triggered by weekend gaps)
    score -= result.safety_events * 5

    return score


def _enqueue_baseline(study: optuna.Study) -> None:
    """Seed trial 0 with baseline (current) friday safety values."""
    enqueue = {
        'friday_safety_max_per_group': FRIDAY_SAFETY_BASELINE['friday_safety_max_per_group'],
        'friday_safety_max_total_non_crypto': FRIDAY_SAFETY_BASELINE['friday_safety_max_total_non_crypto'],
        'friday_safety_r_close_losing': FRIDAY_SAFETY_BASELINE['friday_safety_r_close_losing'],
        'friday_safety_r_new_position': FRIDAY_SAFETY_BASELINE['friday_safety_r_new_position'],
        'friday_safety_r_take_profit': FRIDAY_SAFETY_BASELINE['friday_safety_r_take_profit'],
    }
    study.enqueue_trial(enqueue)


def run_optimization(
    trials: int,
    start: str,
    end: str,
    balance: float = 20000,
    sampler: str = 'tpe',
    output_dir: str = 'backtest/optimization_results',
    n_jobs: int = 1,
    startup_trials: int = 10,
) -> Dict[str, Any]:
    """Run the friday safety optimization study."""

    print("=" * 70)
    print("FRIDAY SAFETY PARAMETER OPTIMIZER")
    print("=" * 70)
    print(f"  Trials: {trials}")
    print(f"  Period: {start} to {end}")
    print(f"  Balance: ${balance:,.0f}")
    print(f"  Sampler: {sampler.upper()}")
    print(f"  Parallel Workers: {n_jobs}")
    print(f"  Random startup trials: {startup_trials}")
    print()
    print("  Optimizing:")
    print(f"    friday_safety_max_per_group:        {FRIDAY_SAFETY_RANGES['friday_safety_max_per_group']}  (baseline: {FRIDAY_SAFETY_BASELINE['friday_safety_max_per_group']})")
    print(f"    friday_safety_max_total_non_crypto: {FRIDAY_SAFETY_RANGES['friday_safety_max_total_non_crypto']}  (baseline: {FRIDAY_SAFETY_BASELINE['friday_safety_max_total_non_crypto']})")
    print(f"    friday_safety_r_close_losing:       {FRIDAY_SAFETY_RANGES['friday_safety_r_close_losing']}  (baseline: {FRIDAY_SAFETY_BASELINE['friday_safety_r_close_losing']})")
    print(f"    friday_safety_r_new_position:       {FRIDAY_SAFETY_RANGES['friday_safety_r_new_position']}  (baseline: {FRIDAY_SAFETY_BASELINE['friday_safety_r_new_position']})")
    print(f"    friday_safety_r_take_profit:        {FRIDAY_SAFETY_RANGES['friday_safety_r_take_profit']}  (baseline: {FRIDAY_SAFETY_BASELINE['friday_safety_r_take_profit']})")
    print("=" * 70)

    study_sampler = TPESampler(seed=42, n_startup_trials=startup_trials)

    study = optuna.create_study(
        direction='maximize',
        sampler=study_sampler,
        study_name=f"friday_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    # Seed trial 0 with baseline params
    _enqueue_baseline(study)

    study.optimize(
        lambda trial: objective(trial, start, end, balance),
        n_trials=trials,
        n_jobs=n_jobs,
        show_progress_bar=True,
        catch=(Exception,),
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
    print(f"  Safety Events: {best.user_attrs.get('safety_events', 0)}")
    print("=" * 70)

    print("\n📊 BEST FRIDAY SAFETY PARAMETERS:")
    for key in [
        'friday_safety_max_per_group',
        'friday_safety_max_total_non_crypto',
        'friday_safety_r_close_losing',
        'friday_safety_r_new_position',
        'friday_safety_r_take_profit',
    ]:
        val = best.params.get(key, FRIDAY_SAFETY_BASELINE.get(key, '?'))
        baseline = FRIDAY_SAFETY_BASELINE.get(key, '?')
        change = " ← changed" if val != baseline else ""
        print(f"    {key}: {val}{change}")

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
    print("ALL TRIALS SUMMARY")
    print("=" * 70)
    print(f"{'#':>3} {'Score':>8} {'Return':>8} {'Trades':>7} {'WR%':>6} {'TDD':>6} {'DDD':>6} {'Safety':>7}")
    print("-" * 70)
    for t in sorted(study.trials, key=lambda x: x.value if x.value else -999, reverse=True)[:20]:
        score = t.value if t.value else -999
        ret = t.user_attrs.get('net_return_pct', 0)
        trades = t.user_attrs.get('total_trades', 0)
        wr = t.user_attrs.get('win_rate', 0)
        tdd = t.user_attrs.get('max_tdd_pct', 0)
        ddd = t.user_attrs.get('max_ddd_pct', 0)
        safety = t.user_attrs.get('safety_events', 0)
        print(f"{t.number:>3} {score:>8.1f} {ret:>+7.1f}% {trades:>7} {wr:>5.1f}% {tdd:>5.1f}% {ddd:>5.1f}% {safety:>7}")
    print("-" * 70)
    if len(study.trials) > 20:
        print(f"  (Showing top 20 of {len(study.trials)} trials)")

    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {
        "optimization_mode": "FRIDAY_SAFETY",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": trials,
            "start": start,
            "end": end,
            "balance": balance,
        },
        "baseline_params": FRIDAY_SAFETY_BASELINE,
        "best_score": best.value,
        "best_metrics": {
            "net_return_pct": best.user_attrs.get('net_return_pct', 0),
            "total_trades": best.user_attrs.get('total_trades', 0),
            "win_rate": best.user_attrs.get('win_rate', 0),
            "max_tdd_pct": best.user_attrs.get('max_tdd_pct', 0),
            "max_ddd_pct": best.user_attrs.get('max_ddd_pct', 0),
            "safety_events": best.user_attrs.get('safety_events', 0),
            "valid": best.user_attrs.get('valid', False),
        },
        "best_parameters": best.params,
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

    results_file = output_path / f"friday_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to: {results_file}")
    print("\n" + "=" * 70)
    print("To apply best parameters to current_params.json, run:")
    print(f"  python backtest/optimize_friday_safety.py --apply {results_file}")
    print("=" * 70)

    return results


def apply_params(results_file: str) -> None:
    """Apply optimized friday safety parameters to current_params.json."""
    from params.params_loader import load_params_dict

    with open(results_file, 'r') as f:
        results = json.load(f)

    best_params = results.get('best_parameters', {})
    friday_params = {k: v for k, v in best_params.items() if k.startswith('friday_safety_')}

    if not friday_params:
        print("ERROR: No friday_safety_* parameters found in results file.")
        sys.exit(1)

    # Load current params and update
    current = load_params_dict()
    if 'parameters' in current:
        current['parameters'].update(friday_params)
    else:
        current.update(friday_params)

    current['optimization_mode'] = "OPTIMIZER_FRIDAY_SAFETY"
    current['timestamp'] = datetime.now().isoformat()
    current['friday_safety_best_score'] = results.get('best_score', 0)

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    print(f"✅ Applied best friday safety parameters to {params_file}")
    print("\nApplied parameters:")
    baseline = results.get('baseline_params', FRIDAY_SAFETY_BASELINE)
    for key, value in sorted(friday_params.items()):
        old_val = baseline.get(key, '?')
        change = f"  (was: {old_val})" if value != old_val else "  (unchanged)"
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}{change}")
        else:
            print(f"  {key}: {value}{change}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Friday Safety Parameter Optimizer')
    parser.add_argument('--trials', type=int, default=50,
                        help='Number of optimization trials (default: 50)')
    parser.add_argument('--start', type=str, default='2024-01-01',
                        help='Backtest start date (default: 2024-01-01)')
    parser.add_argument('--end', type=str, default='2024-12-31',
                        help='Backtest end date (default: 2024-12-31)')
    parser.add_argument('--balance', type=float, default=20000,
                        help='Initial balance (default: 20000)')
    parser.add_argument('--sampler', type=str, default='tpe', choices=['tpe'],
                        help='Optuna sampler (default: tpe)')
    parser.add_argument('--output', type=str, default='backtest/optimization_results',
                        help='Output directory (default: backtest/optimization_results)')
    parser.add_argument('--apply', type=str,
                        help='Apply parameters from results file to current_params.json')
    parser.add_argument('--parallel', '-j', type=int, default=1,
                        help='Number of parallel workers (default: 1)')
    parser.add_argument('--startup-trials', type=int, default=10,
                        help='Random exploration trials before TPE kicks in (default: 10)')

    args = parser.parse_args()

    if args.apply:
        apply_params(args.apply)
    else:
        run_optimization(
            trials=args.trials,
            start=args.start,
            end=args.end,
            balance=args.balance,
            sampler=args.sampler,
            output_dir=args.output,
            n_jobs=args.parallel,
            startup_trials=args.startup_trials,
        )
