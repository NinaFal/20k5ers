#!/usr/bin/env python3
"""
Optimizer for Main Live Bot Backtest

Uses Optuna for hyperparameter optimization with the following objectives:
1. Maximize net return
2. Minimize max drawdown
3. Keep within 5ers limits (TDD < 10%, DDD < 5%)

Parameters to optimize:
- TP levels (TP1 through TP5) - R-multiples
- TP close percentages
- Trailing stop settings
- Confluence thresholds
- Risk per trade

Usage:
    python backtest/optimize_main_live_bot.py --trials 50 --start 2024-01-01 --end 2024-03-31
    python backtest/optimize_main_live_bot.py --trials 100 --start 2023-01-01 --end 2025-12-31 --parallel 4
"""

import sys
import os
import json
import argparse
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import copy

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import optuna
    from optuna.samplers import TPESampler, NSGAIISampler
except ImportError:
    print("ERROR: optuna not installed. Run: pip install optuna")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMIZATION PARAMETER RANGES
# ═══════════════════════════════════════════════════════════════════════════════

# Take Profit R-Multiples (where to place each TP level)
TP_R_RANGES = {
    'tp1_r_multiple': (0.4, 1.0),      # TP1 at 0.4R - 1.0R
    'tp2_r_multiple': (1.0, 2.0),      # TP2 at 1.0R - 2.0R
    'tp3_r_multiple': (1.5, 3.0),      # TP3 at 1.5R - 3.0R
    'tp4_r_multiple': (2.0, 4.0),      # TP4 at 2.0R - 4.0R (optional)
    'tp5_r_multiple': (3.0, 6.0),      # TP5 at 3.0R - 6.0R (optional)
}

# Take Profit Close Percentages (must sum to ~1.0)
TP_CLOSE_RANGES = {
    'tp1_close_pct': (0.20, 0.50),     # Close 20-50% at TP1
    'tp2_close_pct': (0.15, 0.40),     # Close 15-40% at TP2
    'tp3_close_pct': (0.15, 0.40),     # Close 15-40% at TP3
    'tp4_close_pct': (0.05, 0.25),     # Close 5-25% at TP4
    'tp5_close_pct': (0.05, 0.30),     # Close 5-30% at TP5 (remainder)
}

# Trailing Stop Parameters
TRAIL_RANGES = {
    'trail_activation_r': (0.5, 1.5),          # Activate after 0.5R - 1.5R profit
    'atr_trail_multiplier': (1.0, 3.0),        # Trail distance: 1.0-3.0 ATR
    'use_atr_trailing': [True, False],         # Enable/disable trailing
}

# Confluence / Entry Parameters
ENTRY_RANGES = {
    'trend_min_confluence': (4, 8),            # Min confluence in trend mode
    'range_min_confluence': (3, 6),            # Min confluence in range mode
    'min_quality_factors': (2, 5),             # Min quality factors
}

# Risk Parameters
RISK_RANGES = {
    'risk_per_trade_pct': (0.4, 1.0),          # 0.4% - 1.0% risk per trade
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
    valid: bool  # Within 5ers limits?


def create_temp_params_file(params: Dict[str, Any]) -> Path:
    """Create a temporary params file for the backtest."""
    temp_dir = Path(tempfile.gettempdir()) / "optimizer_params"
    temp_dir.mkdir(exist_ok=True)
    
    temp_file = temp_dir / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    
    full_params = {
        "optimization_mode": "OPTIMIZER",
        "timestamp": datetime.now().isoformat(),
        "parameters": params
    }
    
    with open(temp_file, 'w') as f:
        json.dump(full_params, f, indent=2)
    
    return temp_file


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float = 20000) -> OptimizationResult:
    """
    Run backtest with given parameters and return results.
    
    Uses a subprocess to run main_live_bot_backtest.py with modified parameters.
    """
    # Create temporary params file
    temp_params = create_temp_params_file(params)
    
    # Create unique output directory
    output_dir = Path(tempfile.gettempdir()) / "optimizer_results" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Run backtest with custom params file
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "src" / "main_live_bot_backtest.py"),
            "--start", start,
            "--end", end,
            "--balance", str(balance),
            "--output", str(output_dir),
            "--params-file", str(temp_params),
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per backtest
            cwd=str(Path(__file__).parent.parent)
        )
        
        # Parse results from output directory
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
                valid=(data.get('max_tdd_pct', 100) < 10 and data.get('max_ddd_pct', 100) < 5)
            )
        else:
            # Try parsing from stdout
            return parse_stdout_results(result.stdout, params, balance)
            
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ Backtest timed out")
        return OptimizationResult(
            params=params,
            net_return_pct=-100,
            total_trades=0,
            win_rate=0,
            max_tdd_pct=100,
            max_ddd_pct=100,
            final_balance=balance,
            ddd_halts=0,
            valid=False
        )
    except Exception as e:
        print(f"  ⚠️ Backtest error: {e}")
        return OptimizationResult(
            params=params,
            net_return_pct=-100,
            total_trades=0,
            win_rate=0,
            max_tdd_pct=100,
            max_ddd_pct=100,
            final_balance=balance,
            ddd_halts=0,
            valid=False
        )
    finally:
        # Cleanup temp files
        if temp_params.exists():
            temp_params.unlink()


def parse_stdout_results(stdout: str, params: Dict[str, Any], balance: float) -> OptimizationResult:
    """Parse backtest results from stdout."""
    import re
    
    result = OptimizationResult(
        params=params,
        net_return_pct=0,
        total_trades=0,
        win_rate=0,
        max_tdd_pct=100,
        max_ddd_pct=100,
        final_balance=balance,
        ddd_halts=0,
        valid=False
    )
    
    # Parse key metrics from stdout
    patterns = {
        'total_trades': r'Total:\s*(\d+)',
        'win_rate': r'Winners:\s*\d+\s*\((\d+\.?\d*)%\)',
        'net_return_pct': r'Return:\s*\+?(-?\d+\.?\d*)%',
        'final_balance': r'Final:\s*\$?([\d,]+\.?\d*)',
        'max_tdd_pct': r'Max TDD:\s*(\d+\.?\d*)%',
        'max_ddd_pct': r'Max DDD:\s*(\d+\.?\d*)%',
        'ddd_halts': r'DDD halt events:\s*(\d+)',
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, stdout)
        if match:
            value = match.group(1).replace(',', '')
            if field in ['total_trades', 'ddd_halts']:
                setattr(result, field, int(value))
            else:
                setattr(result, field, float(value))
    
    result.valid = (result.max_tdd_pct < 10 and result.max_ddd_pct < 5)
    return result


def sample_tp_params(trial: optuna.Trial, num_tps: int = 3) -> Dict[str, Any]:
    """
    Sample TP parameters ensuring:
    1. R-multiples are in increasing order
    2. Close percentages sum to ~1.0
    """
    params = {}
    
    # Sample R-multiples in order
    prev_r = 0.3
    for i in range(1, num_tps + 1):
        key = f'tp{i}_r_multiple'
        low, high = TP_R_RANGES.get(key, (prev_r + 0.3, prev_r + 2.0))
        low = max(low, prev_r + 0.1)  # Ensure increasing
        r_val = trial.suggest_float(key, low, high, step=0.1)
        params[key] = r_val
        prev_r = r_val
    
    # Sample close percentages that sum to 1.0
    # Strategy: sample weights then normalize
    weights = []
    for i in range(1, num_tps + 1):
        key = f'tp{i}_close_pct'
        low, high = TP_CLOSE_RANGES.get(key, (0.1, 0.5))
        w = trial.suggest_float(f'{key}_weight', low, high, step=0.05)
        weights.append(w)
    
    # Normalize to sum to 1.0
    total = sum(weights)
    for i, w in enumerate(weights, 1):
        params[f'tp{i}_close_pct'] = round(w / total, 3)
    
    return params


def objective(trial: optuna.Trial, start: str, end: str, balance: float, num_tps: int) -> float:
    """
    Optuna objective function.
    
    Returns a score that Optuna tries to MAXIMIZE.
    """
    # Sample TP parameters
    params = sample_tp_params(trial, num_tps)
    
    # Sample trailing stop parameters
    params['trail_activation_r'] = trial.suggest_float(
        'trail_activation_r', 
        TRAIL_RANGES['trail_activation_r'][0],
        TRAIL_RANGES['trail_activation_r'][1],
        step=0.1
    )
    params['atr_trail_multiplier'] = trial.suggest_float(
        'atr_trail_multiplier',
        TRAIL_RANGES['atr_trail_multiplier'][0],
        TRAIL_RANGES['atr_trail_multiplier'][1],
        step=0.1
    )
    params['use_atr_trailing'] = trial.suggest_categorical(
        'use_atr_trailing',
        TRAIL_RANGES['use_atr_trailing']
    )
    
    # Sample confluence parameters
    params['trend_min_confluence'] = trial.suggest_int(
        'trend_min_confluence',
        ENTRY_RANGES['trend_min_confluence'][0],
        ENTRY_RANGES['trend_min_confluence'][1]
    )
    params['range_min_confluence'] = trial.suggest_int(
        'range_min_confluence',
        ENTRY_RANGES['range_min_confluence'][0],
        ENTRY_RANGES['range_min_confluence'][1]
    )
    params['min_quality_factors'] = trial.suggest_int(
        'min_quality_factors',
        ENTRY_RANGES['min_quality_factors'][0],
        ENTRY_RANGES['min_quality_factors'][1]
    )
    
    # Sample risk parameter
    params['risk_per_trade_pct'] = trial.suggest_float(
        'risk_per_trade_pct',
        RISK_RANGES['risk_per_trade_pct'][0],
        RISK_RANGES['risk_per_trade_pct'][1],
        step=0.05
    )
    
    # Run backtest
    print(f"\n  Trial {trial.number}: Running backtest...")
    print(f"    TPs: {params.get('tp1_r_multiple', 0):.1f}R/{params.get('tp2_r_multiple', 0):.1f}R/{params.get('tp3_r_multiple', 0):.1f}R")
    print(f"    Trail: {params.get('trail_activation_r', 0):.1f}R, {params.get('atr_trail_multiplier', 0):.1f}x ATR")
    print(f"    Confluence: T={params.get('trend_min_confluence', 0)}, R={params.get('range_min_confluence', 0)}")
    
    result = run_backtest(params, start, end, balance)
    
    # Store result metrics
    trial.set_user_attr('net_return_pct', result.net_return_pct)
    trial.set_user_attr('total_trades', result.total_trades)
    trial.set_user_attr('win_rate', result.win_rate)
    trial.set_user_attr('max_tdd_pct', result.max_tdd_pct)
    trial.set_user_attr('max_ddd_pct', result.max_ddd_pct)
    trial.set_user_attr('valid', result.valid)
    
    print(f"    → Return: {result.net_return_pct:+.1f}%, Trades: {result.total_trades}, Win: {result.win_rate:.1f}%")
    print(f"    → TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%, Valid: {result.valid}")
    
    # Calculate score
    # Penalize heavily if not within 5ers limits
    if not result.valid:
        return -1000 - result.max_ddd_pct * 10
    
    # Reward return, penalize drawdown
    # Score = return - (max_ddd * 5) - (max_tdd * 2)
    score = result.net_return_pct - (result.max_ddd_pct * 5) - (result.max_tdd_pct * 2)
    
    # Bonus for higher win rate
    if result.win_rate > 55:
        score += (result.win_rate - 55) * 0.5
    
    # Bonus for more trades (more statistical significance)
    if result.total_trades > 100:
        score += min((result.total_trades - 100) * 0.05, 10)
    
    return score


def run_optimization(
    trials: int,
    start: str,
    end: str,
    balance: float = 20000,
    num_tps: int = 3,
    sampler: str = 'tpe',
    output_dir: str = 'backtest/optimization_results'
) -> Dict[str, Any]:
    """Run the optimization study."""
    
    print("=" * 70)
    print("MAIN LIVE BOT BACKTEST OPTIMIZER")
    print("=" * 70)
    print(f"  Trials: {trials}")
    print(f"  Period: {start} to {end}")
    print(f"  Balance: ${balance:,.0f}")
    print(f"  TP Levels: {num_tps}")
    print(f"  Sampler: {sampler.upper()}")
    print("=" * 70)
    
    # Create study
    if sampler == 'nsga':
        study_sampler = NSGAIISampler(seed=42)
    else:
        study_sampler = TPESampler(seed=42)
    
    study = optuna.create_study(
        direction='maximize',
        sampler=study_sampler,
        study_name=f"live_bot_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    
    # Run optimization
    study.optimize(
        lambda trial: objective(trial, start, end, balance, num_tps),
        n_trials=trials,
        show_progress_bar=True,
        catch=(Exception,)
    )
    
    # Get best trial
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
    print("=" * 70)
    
    print("\n📊 BEST PARAMETERS:")
    for key, value in sorted(best.params.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")
    
    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    results = {
        "optimization_mode": sampler.upper(),
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": trials,
            "start": start,
            "end": end,
            "balance": balance,
            "num_tps": num_tps,
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
        "best_parameters": best.params,
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
    
    results_file = output_path / f"optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to: {results_file}")
    
    # Ask to apply best params
    print("\n" + "=" * 70)
    print("To apply best parameters to current_params.json, run:")
    print(f"  python backtest/optimize_main_live_bot.py --apply {results_file}")
    print("=" * 70)
    
    return results


def apply_params(results_file: str):
    """Apply optimized parameters to current_params.json."""
    from params.params_loader import load_params_dict
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    best_params = results.get('best_parameters', {})
    
    # Load current params
    current = load_params_dict()
    if 'parameters' in current:
        current['parameters'].update(best_params)
    else:
        current.update(best_params)
    
    current['optimization_mode'] = "OPTIMIZER"
    current['timestamp'] = datetime.now().isoformat()
    current['best_score'] = results.get('best_score', 0)
    
    # Save
    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)
    
    print(f"✅ Applied best parameters to {params_file}")
    print("\nApplied parameters:")
    for key, value in sorted(best_params.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Optimize Main Live Bot Backtest Parameters')
    parser.add_argument('--trials', type=int, default=50, help='Number of optimization trials')
    parser.add_argument('--start', type=str, default='2024-01-01', help='Backtest start date')
    parser.add_argument('--end', type=str, default='2024-03-31', help='Backtest end date')
    parser.add_argument('--balance', type=float, default=20000, help='Initial balance')
    parser.add_argument('--num-tps', type=int, default=3, choices=[3, 4, 5], help='Number of TP levels (3, 4, or 5)')
    parser.add_argument('--sampler', type=str, default='tpe', choices=['tpe', 'nsga'], help='Optuna sampler')
    parser.add_argument('--output', type=str, default='backtest/optimization_results', help='Output directory')
    parser.add_argument('--apply', type=str, help='Apply parameters from results file')
    
    args = parser.parse_args()
    
    if args.apply:
        apply_params(args.apply)
    else:
        run_optimization(
            trials=args.trials,
            start=args.start,
            end=args.end,
            balance=args.balance,
            num_tps=args.num_tps,
            sampler=args.sampler,
            output_dir=args.output
        )
