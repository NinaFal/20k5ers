#!/usr/bin/env python3
"""
Full Parameter Optimizer – January 2016 to May 2016
====================================================

Optimizes ALL key trading parameters:
  - TP1..TP5 R-multiples        (where to take partials)
  - TP1..TP5 close-percentages  (how much to close at each TP)
  - SL after TP1/TP2/TP3/TP4/TP5 (trailing stop levels)
  - risk_per_trade_pct           (risk per trade)
  - min_confluence               (minimum confluence score)
  - min_quality_factors          (minimum quality factors)
  - adx_trend_threshold          (ADX trend detection)
  - adx_range_threshold          (ADX range detection)
  - trend_min_confluence         (confluence for trend mode)
  - range_min_confluence         (confluence for range mode)
  - atr_trail_multiplier         (ATR trailing stop distance)
  - atr_vol_ratio_range          (ATR volatility ratio for range)
  - atr_min_percentile           (minimum ATR percentile filter)
  - volatile_asset_boost         (scoring boost for volatile assets)
  - entry_fib_level              (Fibonacci retracement entry level)
  - entry_limit_offset_atr       (ATR offset for limit entry)
  - compound_threshold_pct       (compounding profit threshold)

Starts from current params (trial 0 = current_params.json values).

Usage:
    python backtest/optimize_2016_full_params.py
    python backtest/optimize_2016_full_params.py --trials 50 --parallel 3
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

# Take Profit R-Multiples
TP_R_RANGES = {
    'tp1_r_multiple': (0.3, 1.2),
    'tp2_r_multiple': (0.8, 2.6),
    'tp3_r_multiple': (1.2, 3.2),
    'tp4_r_multiple': (1.6, 4.2),
    'tp5_r_multiple': (2.2, 6.0),
}

# Take Profit Close Percentages (normalized to sum to 1.0 via weights)
TP_CLOSE_RANGES = {
    'tp1_close_pct': (0.05, 0.45),
    'tp2_close_pct': (0.10, 0.70),
    'tp3_close_pct': (0.05, 0.45),
    'tp4_close_pct': (0.03, 0.30),
    'tp5_close_pct': (0.03, 0.25),
}

# Strategy & Risk Parameter Ranges
STRATEGY_RANGES = {
    'risk_per_trade_pct':     (0.4, 1.5, 0.05),    # Current: 0.9
    'min_confluence':         (2, 6),                # Current: 3 (int)
    'min_quality_factors':    (2, 7),                # Current: 5 (int)
    'adx_trend_threshold':    (15.0, 30.0, 1.0),    # Current: 21.0
    'adx_range_threshold':    (8.0, 20.0, 1.0),     # Current: 14.0
    'trend_min_confluence':   (3, 7),                # Current: 4 (int)
    'range_min_confluence':   (2, 6),                # Current: 5 (int)
    'atr_trail_multiplier':   (1.0, 4.0, 0.1),      # Current: 2.9
    'atr_vol_ratio_range':    (0.4, 1.5, 0.1),      # Current: 0.8
    'atr_min_percentile':     (15.0, 60.0, 1.0),    # Current: 35.0
    'volatile_asset_boost':   (1.0, 2.0, 0.05),     # Current: 1.3
    'entry_fib_level':        (0.382, 0.786, 0.01),  # Current: 0.560
    'entry_limit_offset_atr': (0.0, 0.5, 0.01),     # Current: 0.14
    'compound_threshold_pct': (2.0, 15.0, 0.5),     # Current: 5.5
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
    monthly_stats: Dict[str, Any] = None
    safety_events: int = 0
    tdd_warnings: int = 0


def load_current_params() -> Dict[str, Any]:
    """Load non-optimized params from current_params.json to pass through unchanged."""
    from params.params_loader import load_params_dict
    raw = load_params_dict()
    return raw.get('parameters', raw)


def create_temp_params_file(params: Dict[str, Any]) -> Path:
    """Create a temporary params file for the backtest."""
    temp_dir = Path(tempfile.gettempdir()) / "optimizer_full_params"
    temp_dir.mkdir(exist_ok=True)

    temp_file = temp_dir / f"params_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"

    full_params = {
        "optimization_mode": "OPTIMIZER_FULL",
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
    temp_params = create_temp_params_file(params)

    output_dir = Path(tempfile.gettempdir()) / "optimizer_full_results" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
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
                tdd_warnings=data.get('tdd_warnings', 0)
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
    """Parse backtest results from stdout."""
    import re

    result = OptimizationResult(
        params=params, net_return_pct=0, total_trades=0, win_rate=0,
        max_tdd_pct=100, max_ddd_pct=100, final_balance=balance, ddd_halts=0, valid=False
    )

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


def sample_strategy_params(trial: optuna.Trial) -> Dict[str, Any]:
    """
    Sample strategy & risk parameters.

    Float params use suggest_float with step, int params use suggest_int.
    """
    params = {}

    for key, bounds in STRATEGY_RANGES.items():
        if len(bounds) == 2:
            # Integer parameter
            lo, hi = bounds
            params[key] = trial.suggest_int(key, lo, hi)
        else:
            # Float parameter with step
            lo, hi, step = bounds
            params[key] = trial.suggest_float(key, lo, hi, step=step)

    return params


def sample_tp_and_sl_params(trial: optuna.Trial, num_tps: int = 5) -> Dict[str, Any]:
    """
    Sample TP R-multiples, close percentages, and SL-after-TP levels.

    TP R-multiples: sampled in strictly increasing order.
    Close percentages: sampled as weights, then normalized to sum to 1.0.
    SL after TP1: between 0.0 and tp1_r (optimized, not hardcoded)
    SL after TP2: between tp1_r and tp2_r
    SL after TP3: between tp1_r and tp3_r
    SL after TP4: between tp2_r and tp4_r
    SL after TP5: between tp3_r and tp5_r
    """
    params = {}

    # ── TP R-multiples (strictly increasing) ──────────────────────────────────
    prev_r = 0.3
    tp_r_values = []
    for i in range(1, num_tps + 1):
        key = f'tp{i}_r_multiple'
        low, high = TP_R_RANGES.get(key, (prev_r + 0.3, prev_r + 2.0))
        low = max(low, prev_r + 0.1)  # Ensure strictly increasing
        r_val = trial.suggest_float(key, low, high, step=0.1)
        params[key] = r_val
        tp_r_values.append(r_val)
        prev_r = r_val

    tp1_r, tp2_r, tp3_r = tp_r_values[0], tp_r_values[1], tp_r_values[2]
    tp4_r = tp_r_values[3] if num_tps >= 4 else tp3_r
    tp5_r = tp_r_values[4] if num_tps >= 5 else tp4_r

    # ── Close percentages (normalized to sum 1.0) ─────────────────────────────
    weights = []
    for i in range(1, num_tps + 1):
        key = f'tp{i}_close_pct'
        low, high = TP_CLOSE_RANGES.get(key, (0.05, 0.40))
        w = trial.suggest_float(f'{key}_weight', low, high, step=0.05)
        weights.append(w)

    total = sum(weights)
    for i, w in enumerate(weights, 1):
        params[f'tp{i}_close_pct'] = round(w / total, 3)

    # ── SL levels after each TP hit ───────────────────────────────────────────
    def sl_range(lo, hi):
        if hi - lo < 0.1:
            hi = lo + 0.1
        return lo, hi

    # SL after TP1: between 0.0R (breakeven) and tp1_r
    params['sl_after_tp1_r'] = trial.suggest_float('sl_after_tp1_r', 0.0, max(tp1_r, 0.1), step=0.05)

    # SL after TP2: between tp1_r and tp2_r
    params['sl_after_tp2_r'] = trial.suggest_float('sl_after_tp2_r', *sl_range(tp1_r, tp2_r), step=0.05)

    # SL after TP3: between tp1_r and tp3_r
    params['sl_after_tp3_r'] = trial.suggest_float('sl_after_tp3_r', *sl_range(tp1_r, tp3_r), step=0.05)

    # SL after TP4: between tp2_r and tp4_r
    params['sl_after_tp4_r'] = trial.suggest_float('sl_after_tp4_r', *sl_range(tp2_r, tp4_r), step=0.05)

    # SL after TP5: between tp3_r and tp5_r
    params['sl_after_tp5_r'] = trial.suggest_float('sl_after_tp5_r', *sl_range(tp3_r, tp5_r), step=0.05)

    return params


def objective(trial: optuna.Trial, start: str, end: str, balance: float, num_tps: int,
              base_params: Dict[str, Any]) -> float:
    """
    Optuna objective function.

    Samples TP/SL params AND strategy/risk params.
    Remaining params come from base_params (current_params.json).
    Returns a score that Optuna tries to MAXIMIZE.
    """
    # Start from current params (non-optimized params pass through unchanged)
    params = dict(base_params)

    # Sample and overlay TP/SL params
    tp_sl_params = sample_tp_and_sl_params(trial, num_tps)
    params.update(tp_sl_params)

    # Sample and overlay strategy/risk params
    strat_params = sample_strategy_params(trial)
    params.update(strat_params)

    # Print trial summary
    print(f"\n  Trial {trial.number}: Running backtest...")
    print(f"    TPs: {params.get('tp1_r_multiple', 0):.1f}R / {params.get('tp2_r_multiple', 0):.1f}R / "
          f"{params.get('tp3_r_multiple', 0):.1f}R / {params.get('tp4_r_multiple', 0):.1f}R / "
          f"{params.get('tp5_r_multiple', 0):.1f}R")
    print(f"    Close%: {params.get('tp1_close_pct', 0):.0%} / {params.get('tp2_close_pct', 0):.0%} / "
          f"{params.get('tp3_close_pct', 0):.0%} / {params.get('tp4_close_pct', 0):.0%} / "
          f"{params.get('tp5_close_pct', 0):.0%}")
    print(f"    SL after TP1={params.get('sl_after_tp1_r', 0):.2f}R | TP2={params.get('sl_after_tp2_r', 0):.2f}R | "
          f"TP3={params.get('sl_after_tp3_r', 0):.2f}R | TP4={params.get('sl_after_tp4_r', 0):.2f}R | "
          f"TP5={params.get('sl_after_tp5_r', 0):.2f}R")
    print(f"    Risk={params.get('risk_per_trade_pct', 0):.2f}% | Confl={params.get('min_confluence', 0)} | "
          f"QF={params.get('min_quality_factors', 0)} | ADX-T={params.get('adx_trend_threshold', 0):.0f} | "
          f"ADX-R={params.get('adx_range_threshold', 0):.0f}")
    print(f"    ATR-trail={params.get('atr_trail_multiplier', 0):.1f} | Fib={params.get('entry_fib_level', 0):.3f} | "
          f"Offset={params.get('entry_limit_offset_atr', 0):.2f} | Compound={params.get('compound_threshold_pct', 0):.1f}%")

    result = run_backtest(params, start, end, balance)

    # Store result metrics
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

    # ── Scoring ───────────────────────────────────────────────────────────────
    if not result.valid:
        return -1000 - result.max_ddd_pct * 10

    if result.max_ddd_pct >= 5.0:
        return -500 - result.max_ddd_pct * 20

    if result.total_trades < 10:
        return -500 + result.total_trades

    win_rate_factor = result.win_rate / 100.0
    if win_rate_factor >= 0.5:
        wr_multiplier = 0.5 + (win_rate_factor * 1.5)
    else:
        wr_multiplier = win_rate_factor

    trade_bonus = min(result.total_trades / 5, 20)

    score = (
        result.net_return_pct * wr_multiplier +
        trade_bonus
    )

    if result.max_tdd_pct > 5.0:
        score -= (result.max_tdd_pct - 5.0) * 15

    if result.ddd_halts == 0 and result.max_ddd_pct < 2.5:
        score += 10

    return score


def _enqueue_current_params(study: optuna.Study, num_tps: int, base_params: Dict[str, Any]) -> None:
    """Seed trial 0 with current_params.json values for ALL optimized params."""
    enqueue_params: Dict[str, Any] = {}

    # TP R-multiples
    prev_r = 0.3
    tp_r_values = []
    for i in range(1, num_tps + 1):
        key = f'tp{i}_r_multiple'
        val = base_params.get(key)
        if val is not None:
            enqueue_params[key] = val
            tp_r_values.append(val)
            prev_r = val
        else:
            tp_r_values.append(prev_r + 0.5)

    # Close percentages as weights (normalization preserves ratios)
    for i in range(1, num_tps + 1):
        key = f'tp{i}_close_pct'
        weight_key = f'{key}_weight'
        if key in base_params:
            enqueue_params[weight_key] = base_params[key]

    # SL after each TP hit
    tp1_r = tp_r_values[0] if len(tp_r_values) > 0 else 0.6
    tp2_r = tp_r_values[1] if len(tp_r_values) > 1 else 1.1
    tp3_r = tp_r_values[2] if len(tp_r_values) > 2 else 1.8

    enqueue_params['sl_after_tp1_r'] = base_params.get('sl_after_tp1_r', 0.05)
    enqueue_params['sl_after_tp2_r'] = base_params.get('sl_after_tp2_r', tp1_r)
    enqueue_params['sl_after_tp3_r'] = base_params.get('sl_after_tp3_r', tp1_r)
    enqueue_params['sl_after_tp4_r'] = base_params.get('sl_after_tp4_r', tp2_r)
    enqueue_params['sl_after_tp5_r'] = base_params.get('sl_after_tp5_r', tp3_r)

    # Strategy/risk params – seed with current values
    for key in STRATEGY_RANGES:
        if key in base_params:
            enqueue_params[key] = base_params[key]

    if enqueue_params:
        study.enqueue_trial(enqueue_params)


def run_optimization(
    trials: int,
    start: str,
    end: str,
    balance: float = 20000,
    num_tps: int = 5,
    sampler: str = 'tpe',
    output_dir: str = 'backtest/optimization_results/2016_full_params',
    n_jobs: int = 3,
    startup_trials: int = 10,
) -> Dict[str, Any]:
    """Run the optimization study."""

    # Load current (non-optimized) params to pass through unchanged
    base_params = load_current_params()

    print("=" * 70)
    print("FULL PARAMETER OPTIMIZER – January 2016 to May 2016")
    print("=" * 70)
    print(f"  Trials: {trials}")
    print(f"  Period: {start} to {end}")
    print(f"  Balance: ${balance:,.0f}")
    print(f"  TP Levels: {num_tps}")
    print(f"  Sampler: {sampler.upper()}")
    print(f"  Parallel Workers: {n_jobs}")
    print(f"  Timeout: NONE (runs until all trials complete)")
    print("  Optimizing: TP/SL levels + strategy/risk params")
    print(f"  Random startup trials: {startup_trials}")
    print("=" * 70)

    current_tps = [base_params.get(f'tp{i}_r_multiple', '?') for i in range(1, 6)]
    print(f"  Current TPs: {' / '.join(str(r) for r in current_tps)}")
    print(f"  Current close%: {' / '.join(str(base_params.get(f'tp{i}_close_pct', '?')) for i in range(1, 6))}")
    print(f"  Current risk: {base_params.get('risk_per_trade_pct', '?')}%")
    print(f"  Current confluence: {base_params.get('min_confluence', '?')} | QF: {base_params.get('min_quality_factors', '?')}")
    print(f"  Current ADX trend/range: {base_params.get('adx_trend_threshold', '?')} / {base_params.get('adx_range_threshold', '?')}")
    print(f"  Current ATR trail: {base_params.get('atr_trail_multiplier', '?')} | Fib: {base_params.get('entry_fib_level', '?')}")
    print(f"  Current compound: {base_params.get('compound_threshold_pct', '?')}%")
    print("=" * 70)

    if sampler == 'nsga':
        study_sampler = NSGAIISampler(seed=42)
    else:
        study_sampler = TPESampler(seed=42, n_startup_trials=startup_trials)

    study = optuna.create_study(
        direction='maximize',
        sampler=study_sampler,
        study_name=f"full_param_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Seed trial 0 with current params
    _enqueue_current_params(study, num_tps, base_params)

    # Run optimization – NO timeout
    study.optimize(
        lambda trial: objective(trial, start, end, balance, num_tps, base_params),
        n_trials=trials,
        n_jobs=n_jobs,
        timeout=None,
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

    # Reconstruct best TP/SL params from best trial
    best_tp_r = {f'tp{i}_r_multiple': best.params.get(f'tp{i}_r_multiple') for i in range(1, num_tps + 1)}
    # Reconstruct normalized close pcts
    weights = [best.params.get(f'tp{i}_close_pct_weight', 1.0) for i in range(1, num_tps + 1)]
    total_w = sum(weights)
    best_close = {f'tp{i}_close_pct': round(w / total_w, 3) for i, w in enumerate(weights, 1)}

    print("\n📊 BEST TP/SL PARAMETERS:")
    print("  TP R-multiples:")
    for i in range(1, num_tps + 1):
        print(f"    tp{i}_r_multiple: {best_tp_r.get(f'tp{i}_r_multiple', '?'):.2f}R")
    print("  Close percentages:")
    for i in range(1, num_tps + 1):
        print(f"    tp{i}_close_pct: {best_close.get(f'tp{i}_close_pct', '?'):.1%}")
    print("  SL after each TP:")
    print(f"    sl_after_tp1_r: {best.params.get('sl_after_tp1_r', '?'):.2f}R")
    for sl_key in ['sl_after_tp2_r', 'sl_after_tp3_r', 'sl_after_tp4_r', 'sl_after_tp5_r']:
        print(f"    {sl_key}: {best.params.get(sl_key, '?'):.2f}R")

    print("\n📊 BEST STRATEGY/RISK PARAMETERS:")
    for key in STRATEGY_RANGES:
        val = best.params.get(key, '?')
        if isinstance(val, float):
            print(f"    {key}: {val:.4f}")
        else:
            print(f"    {key}: {val}")

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

    results = {
        "optimization_mode": sampler.upper(),
        "optimization_scope": "FULL_PARAMS",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": trials,
            "start": start,
            "end": end,
            "balance": balance,
            "num_tps": num_tps,
            "n_jobs": n_jobs,
            "timeout": None,
        },
        "optimized_param_keys": list(TP_R_RANGES.keys()) + list(TP_CLOSE_RANGES.keys()) +
                                 ['sl_after_tp1_r', 'sl_after_tp2_r', 'sl_after_tp3_r',
                                  'sl_after_tp4_r', 'sl_after_tp5_r'] +
                                 list(STRATEGY_RANGES.keys()),
        "best_score": best.value,
        "best_metrics": {
            "net_return_pct": best.user_attrs.get('net_return_pct', 0),
            "total_trades": best.user_attrs.get('total_trades', 0),
            "win_rate": best.user_attrs.get('win_rate', 0),
            "max_tdd_pct": best.user_attrs.get('max_tdd_pct', 0),
            "max_ddd_pct": best.user_attrs.get('max_ddd_pct', 0),
            "valid": best.user_attrs.get('valid', False),
        },
        "best_parameters": {
            **best.params,
            **best_close,
        },
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
    print("\n" + "=" * 70)
    print("To apply best parameters to current_params.json, run:")
    print(f"  python backtest/optimize_2016_full_params.py --apply {results_file}")
    print("=" * 70)

    return results


def apply_params(results_file: str):
    """Apply optimized parameters to current_params.json."""
    from params.params_loader import load_params_dict

    with open(results_file, 'r') as f:
        results = json.load(f)

    best_params_raw = results.get('best_parameters', {})

    # Reconstruct normalized close percentages from weights if needed
    weights = [best_params_raw.get(f'tp{i}_close_pct_weight', None) for i in range(1, 6)]
    if any(w is not None for w in weights):
        valid_weights = [w if w is not None else 0.0 for w in weights]
        total_w = sum(valid_weights) or 1.0
        for i, w in enumerate(valid_weights, 1):
            best_params_raw[f'tp{i}_close_pct'] = round(w / total_w, 3)

    # Apply all keys except internal weight keys
    apply_keys = {k: v for k, v in best_params_raw.items()
                  if not k.endswith('_weight')}

    # Load current params
    current = load_params_dict()
    if 'parameters' in current:
        current['parameters'].update(apply_keys)
    else:
        current.update(apply_keys)

    current['optimization_mode'] = "OPTIMIZER_FULL_PARAMS"
    current['timestamp'] = datetime.now().isoformat()
    current['best_score'] = results.get('best_score', 0)

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    print(f"✅ Applied best parameters to {params_file}")
    print("\nApplied parameters:")
    for key, value in sorted(apply_keys.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Full Parameter Optimizer – Jan-May 2016')
    parser.add_argument('--trials', type=int, default=50, help='Number of optimization trials (default: 50)')
    parser.add_argument('--start', type=str, default='2016-01-01', help='Backtest start date')
    parser.add_argument('--end', type=str, default='2016-05-31', help='Backtest end date')
    parser.add_argument('--balance', type=float, default=20000, help='Initial balance')
    parser.add_argument('--num-tps', type=int, default=5, choices=[3, 4, 5], help='Number of TP levels')
    parser.add_argument('--sampler', type=str, default='tpe', choices=['tpe', 'nsga'], help='Optuna sampler')
    parser.add_argument('--output', type=str, default='backtest/optimization_results/2016_full_params',
                        help='Output directory')
    parser.add_argument('--apply', type=str, help='Apply parameters from results file')
    parser.add_argument('--parallel', '-j', type=int, default=3, help='Number of parallel workers (default: 3)')
    parser.add_argument('--startup-trials', type=int, default=10,
                        help='Number of random exploration trials before TPE kicks in (default: 10)')

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
            output_dir=args.output,
            n_jobs=args.parallel,
            startup_trials=args.startup_trials,
        )
