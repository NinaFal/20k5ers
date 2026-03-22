#!/usr/bin/env python3
"""
Friday Safety Parameter Optimizer

Mirrors optimize_main_live_bot.py structure exactly. Runs main_live_bot_backtest.py
(M15-based) as a subprocess for each trial, injecting friday safety params via a
temp params file alongside all current StrategyParams (unchanged).

Optimizes:
- friday_safety_max_per_group        (int 1-4):  max positions per correlation group
- friday_safety_max_total_non_crypto (int 1-8):  max non-crypto positions over weekend
- friday_safety_r_close_losing       (float):    close positions below this R (default 0.0)
- friday_safety_r_new_position       (float):    reduce 50% below / hold above (default 0.5)

ALL strategy params (TP/SL, confluence, risk, etc.) are loaded from
current_params.json and passed through unchanged.

Starts from baseline values (trial 0 = current defaults).

Usage:
    python backtest/optimize_friday_safety.py --trials 50 --start 2016-01-01 --end 2016-05-31
    python backtest/optimize_friday_safety.py --trials 100 --start 2023-01-01 --end 2025-12-31 --parallel 4
    python backtest/optimize_friday_safety.py --apply backtest/optimization_results/friday_safety_YYYYMMDD.json
"""

import sys
import os
import json
import argparse
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import copy

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import optuna
    from optuna.samplers import TPESampler, NSGAIISampler
except ImportError:
    print("ERROR: optuna not installed. Run: pip install optuna")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# FRIDAY SAFETY PARAMETER RANGES
# Baseline = current hardcoded defaults
# ═══════════════════════════════════════════════════════════════════════════════

FRIDAY_SAFETY_RANGES = {
    'friday_safety_max_per_group':        (1, 4),       # Baseline: 2
    'friday_safety_max_total_non_crypto': (1, 8),       # Baseline: 5
    'friday_safety_r_close_losing':       (-0.5, 0.2),  # Baseline: 0.0
    'friday_safety_r_new_position':       (0.1, 1.0),   # Baseline: 0.5
    'friday_safety_reduce_pct':           (0.05, 0.50), # Baseline: 0.50 (5%-50%)
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
    valid: bool
    monthly_stats: Dict[str, Any] = None
    safety_events: int = 0
    tdd_warnings: int = 0


def load_current_params() -> Dict[str, Any]:
    """Load all current strategy params from current_params.json (pass-through unchanged)."""
    from params.params_loader import load_params_dict
    raw = load_params_dict()
    return raw.get('parameters', raw)


def create_temp_params_file(params: Dict[str, Any]) -> Path:
    """Create a temporary params file for the backtest subprocess."""
    temp_dir = Path(tempfile.gettempdir()) / "friday_optimizer_params"
    temp_dir.mkdir(exist_ok=True)

    temp_file = temp_dir / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"

    full_params = {
        "optimization_mode": "FRIDAY_SAFETY_OPTIMIZER",
        "timestamp": datetime.now().isoformat(),
        "parameters": params
    }

    with open(temp_file, 'w') as f:
        json.dump(full_params, f, indent=2)

    return temp_file


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float = 20000) -> OptimizationResult:
    """
    Run main_live_bot_backtest.py (M15-based) as a subprocess with given params.
    Identical call pattern to optimize_main_live_bot.py.
    """
    temp_params = create_temp_params_file(params)

    output_dir = (Path(tempfile.gettempdir()) / "friday_optimizer_results" /
                  f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}")
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
            cwd=str(Path(__file__).parent.parent)
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
                valid=(data.get('max_tdd_pct', 100) < 10 and data.get('max_ddd_pct', 100) < 5),
                monthly_stats=data.get('monthly_stats', {}),
                safety_events=data.get('safety_events', data.get('ddd_halts', 0)),
                tdd_warnings=data.get('tdd_warnings', 0),
            )
        else:
            return parse_stdout_results(result.stdout, params, balance)

    except Exception as e:
        print(f"  ⚠️ Backtest error: {e}")
        return OptimizationResult(
            params=params, net_return_pct=-100, total_trades=0, win_rate=0,
            max_tdd_pct=100, max_ddd_pct=100, final_balance=balance, ddd_halts=0, valid=False
        )
    finally:
        if temp_params.exists():
            temp_params.unlink()


def parse_stdout_results(stdout: str, params: Dict[str, Any], balance: float) -> OptimizationResult:
    """Parse backtest results from stdout (fallback)."""
    import re

    result = OptimizationResult(
        params=params, net_return_pct=0, total_trades=0, win_rate=0,
        max_tdd_pct=100, max_ddd_pct=100, final_balance=balance, ddd_halts=0, valid=False
    )

    patterns = {
        'total_trades':   r'Total:\s*(\d+)',
        'win_rate':       r'Winners:\s*\d+\s*\((\d+\.?\d*)%\)',
        'net_return_pct': r'Return:\s*\+?(-?\d+\.?\d*)%',
        'final_balance':  r'Final:\s*\$?([\d,]+\.?\d*)',
        'max_tdd_pct':    r'Max TDD:\s*(\d+\.?\d*)%',
        'max_ddd_pct':    r'Max DDD:\s*(\d+\.?\d*)%',
        'ddd_halts':      r'DDD halt events:\s*(\d+)',
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, stdout)
        if match:
            value = match.group(1).replace(',', '')
            setattr(result, field, int(value) if field in ('total_trades', 'ddd_halts') else float(value))

    result.valid = (result.max_tdd_pct < 10 and result.max_ddd_pct < 5)
    return result


def sample_friday_safety_params(trial: optuna.Trial) -> Dict[str, Any]:
    """Sample all friday safety parameters for a trial."""
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
    r_cl = params['friday_safety_r_close_losing']
    r_np_low  = max(FRIDAY_SAFETY_RANGES['friday_safety_r_new_position'][0], r_cl + 0.1)
    r_np_high = FRIDAY_SAFETY_RANGES['friday_safety_r_new_position'][1]
    if r_np_high < r_np_low + 0.1:
        r_np_high = r_np_low + 0.1
    params['friday_safety_r_new_position'] = trial.suggest_float(
        'friday_safety_r_new_position', r_np_low, r_np_high, step=0.05,
    )
    params['friday_safety_reduce_pct'] = trial.suggest_float(
        'friday_safety_reduce_pct',
        FRIDAY_SAFETY_RANGES['friday_safety_reduce_pct'][0],
        FRIDAY_SAFETY_RANGES['friday_safety_reduce_pct'][1],
        step=0.05,
    )
    return params


def objective(trial: optuna.Trial, start: str, end: str, balance: float,
              base_params: Dict[str, Any]) -> float:
    """
    Optuna objective function.

    Samples friday safety params and overlays them on base_params (current_params.json).
    All strategy params (TP/SL, confluence, etc.) pass through unchanged.
    Returns a score that Optuna tries to MAXIMIZE.
    """
    params = dict(base_params)

    friday_params = sample_friday_safety_params(trial)
    params.update(friday_params)

    print(f"\n  Trial {trial.number}: Running backtest...")
    print(f"    max_per_group={params['friday_safety_max_per_group']}  "
          f"max_total_non_crypto={params['friday_safety_max_total_non_crypto']}")
    print(f"    r_close_losing={params['friday_safety_r_close_losing']:.2f}R  "
          f"r_new_position={params['friday_safety_r_new_position']:.2f}R")

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
    trial.set_user_attr('tdd_warnings', result.tdd_warnings)
    trial.set_user_attr('valid', result.valid)

    print(f"    → Return: {result.net_return_pct:+.1f}%, Trades: {result.total_trades}, Win: {result.win_rate:.1f}%")
    print(f"    → TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%, DDD Halts: {result.ddd_halts}, Valid: {result.valid}")

    # ── Scoring (mirrors optimize_main_live_bot.py) ────────────────────────────
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

    # Penalise weekend safety events
    score -= result.safety_events * 5

    return score


def _enqueue_baseline(study: optuna.Study, base_params: Dict[str, Any]) -> None:
    """Seed trial 0 with current baseline friday safety values."""
    enqueue = {
        'friday_safety_max_per_group':        int(base_params.get('friday_safety_max_per_group', 2)),
        'friday_safety_max_total_non_crypto': int(base_params.get('friday_safety_max_total_non_crypto', 5)),
        'friday_safety_r_close_losing':       float(base_params.get('friday_safety_r_close_losing', 0.0)),
        'friday_safety_r_new_position':       float(base_params.get('friday_safety_r_new_position', 0.5)),
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

    base_params = load_current_params()

    print("=" * 70)
    print("FRIDAY SAFETY OPTIMIZER (main_live_bot_backtest / M15)")
    print("=" * 70)
    print(f"  Trials: {trials}")
    print(f"  Period: {start} to {end}")
    print(f"  Balance: ${balance:,.0f}")
    print(f"  Sampler: {sampler.upper()}")
    print(f"  Parallel Workers: {n_jobs}")
    print(f"  Random startup trials: {startup_trials}")
    print()
    DEFAULTS = {
        'friday_safety_max_per_group': 2,
        'friday_safety_max_total_non_crypto': 5,
        'friday_safety_r_close_losing': 0.0,
        'friday_safety_r_new_position': 0.5,
        'friday_safety_reduce_pct': 0.50,
    }
    print("  Optimizing:")
    for key, val in FRIDAY_SAFETY_RANGES.items():
        lo, hi = val
        baseline = base_params.get(key, DEFAULTS.get(key, '?'))
        print(f"    {key:<44} range [{lo}, {hi}]  baseline: {baseline}")
    print("  Fixed (from current_params.json): all strategy params (TP/SL, confluence, risk, ...)")
    print("=" * 70)

    if sampler == 'nsga':
        study_sampler = NSGAIISampler(seed=42)
    else:
        study_sampler = TPESampler(seed=42, n_startup_trials=startup_trials)

    study = optuna.create_study(
        direction='maximize',
        sampler=study_sampler,
        study_name=f"friday_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    _enqueue_baseline(study, base_params)

    study.optimize(
        lambda trial: objective(trial, start, end, balance, base_params),
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
    all_keys = list(FRIDAY_SAFETY_RANGES.keys())
    for key in all_keys:
        val = best.params.get(key, '?')
        baseline = base_params.get(key, '?')
        change = "  ← changed" if val != baseline else ""
        fmt = f"{val:.3f}" if isinstance(val, float) else str(val)
        print(f"    {key}: {fmt}{change}")

    # Monthly breakdown
    monthly = best.user_attrs.get('monthly_stats', {})
    if monthly:
        print("\n📅 MONTHLY BREAKDOWN (Best Trial):")
        print("  " + "-" * 60)
        print(f"  {'Month':<10} {'Trades':>8} {'Winners':>8} {'Win%':>8} {'PnL':>12}")
        print("  " + "-" * 60)
        for month in sorted(monthly.keys()):
            m = monthly[month]
            trades  = m.get('trades', 0)
            winners = m.get('winners', 0)
            pnl     = m.get('pnl', 0)
            wr      = (winners / trades * 100) if trades > 0 else 0
            print(f"  {month:<10} {trades:>8} {winners:>8} {wr:>7.1f}% ${pnl:>10,.0f}")
        print("  " + "-" * 60)

    # All trials summary
    print("\n" + "=" * 70)
    print("ALL TRIALS SUMMARY")
    print("=" * 70)
    print(f"{'#':>3} {'Score':>8} {'Return':>8} {'Trades':>7} {'WR%':>6} {'TDD':>6} {'DDD':>6} {'Safe':>5}")
    print("-" * 70)
    for t in sorted(study.trials, key=lambda x: x.value if x.value else -999, reverse=True)[:20]:
        score  = t.value if t.value else -999
        ret    = t.user_attrs.get('net_return_pct', 0)
        trades = t.user_attrs.get('total_trades', 0)
        wr     = t.user_attrs.get('win_rate', 0)
        tdd    = t.user_attrs.get('max_tdd_pct', 0)
        ddd    = t.user_attrs.get('max_ddd_pct', 0)
        safe   = t.user_attrs.get('safety_events', t.user_attrs.get('ddd_halts', 0))
        print(f"{t.number:>3} {score:>8.1f} {ret:>+7.1f}% {trades:>7} {wr:>5.1f}% {tdd:>5.1f}% {ddd:>5.1f}% {safe:>5}")
    print("-" * 70)
    if len(study.trials) > 20:
        print(f"  (Showing top 20 of {len(study.trials)} trials)")

    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {
        "optimization_mode": "FRIDAY_SAFETY",
        "optimization_scope": "FRIDAY_SAFETY_PARAMS",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": trials,
            "start": start,
            "end": end,
            "balance": balance,
        },
        "fixed_params": {k: v for k, v in base_params.items() if not k.startswith('friday_safety_')},
        "best_score": best.value,
        "best_metrics": {
            "net_return_pct":  best.user_attrs.get('net_return_pct', 0),
            "total_trades":    best.user_attrs.get('total_trades', 0),
            "win_rate":        best.user_attrs.get('win_rate', 0),
            "max_tdd_pct":     best.user_attrs.get('max_tdd_pct', 0),
            "max_ddd_pct":     best.user_attrs.get('max_ddd_pct', 0),
            "safety_events":   best.user_attrs.get('safety_events', 0),
            "valid":           best.user_attrs.get('valid', False),
        },
        "best_parameters": best.params,
        "all_trials": [
            {
                "trial":   t.number,
                "score":   t.value if t.value is not None else -1000,
                "params":  t.params,
                "metrics": dict(t.user_attrs),
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

    best_params_raw = results.get('best_parameters', {})
    friday_params = {k: v for k, v in best_params_raw.items() if k.startswith('friday_safety_')}

    if not friday_params:
        print("ERROR: No friday_safety_* parameters found in results file.")
        sys.exit(1)

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
    for key, value in sorted(friday_params.items()):
        fmt = f"{value:.3f}" if isinstance(value, float) else str(value)
        print(f"  {key}: {fmt}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Friday Safety Parameter Optimizer (M15 backtest)')
    parser.add_argument('--trials',         type=int,   default=50,
                        help='Number of optimization trials (default: 50)')
    parser.add_argument('--start',          type=str,   default='2024-01-01',
                        help='Backtest start date (default: 2024-01-01)')
    parser.add_argument('--end',            type=str,   default='2024-12-31',
                        help='Backtest end date (default: 2024-12-31)')
    parser.add_argument('--balance',        type=float, default=20000,
                        help='Initial balance (default: 20000)')
    parser.add_argument('--sampler',        type=str,   default='tpe', choices=['tpe', 'nsga'],
                        help='Optuna sampler (default: tpe)')
    parser.add_argument('--output',         type=str,   default='backtest/optimization_results',
                        help='Output directory (default: backtest/optimization_results)')
    parser.add_argument('--apply',          type=str,
                        help='Apply parameters from results file to current_params.json')
    parser.add_argument('--parallel', '-j', type=int,   default=1,
                        help='Number of parallel workers (default: 1)')
    parser.add_argument('--startup-trials', type=int,   default=10,
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
