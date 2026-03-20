#!/usr/bin/env python3
"""
Optimizer for Main Live Bot Backtest - TP/SL levels only

Optimizes ONLY:
- TP1..TP5 R-multiples (where to take partials)
- TP1..TP5 close percentages (how much to close at each TP)
- SL after TP2 (between TP1 and TP2)
- SL after TP3 (between TP1 and TP3)
- SL after TP4 (between TP2 and TP4)
- SL after TP5 (between TP3 and TP5)

HARDCODED (not optimized):
- SL after TP1: always 0.05R (breakeven + fees)

ALL other params (confluence, risk, trailing stop, entry refinement, compounding)
are loaded from current_params.json and passed through unchanged.

Starts from current params (trial 0 = current_params.json values).

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
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import copy

_print_lock = threading.Lock()

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
# Current params (baseline): tp1=0.6, tp2=1.1, tp3=1.8, tp4=2.3, tp5=2.8
# ═══════════════════════════════════════════════════════════════════════════════

# Take Profit R-Multiples
TP_R_RANGES = {
    'tp1_r_multiple': (0.3, 1.2),      # Baseline: 0.6
    'tp2_r_multiple': (0.8, 2.6),      # Baseline: 1.1
    'tp3_r_multiple': (1.2, 3.2),      # Baseline: 1.8
    'tp4_r_multiple': (1.6, 4.2),      # Baseline: 2.3
    'tp5_r_multiple': (2.2, 6.0),      # Baseline: 2.8
}

# Take Profit Close Percentages (normalized to sum to 1.0 via weights)
TP_CLOSE_RANGES = {
    'tp1_close_pct': (0.05, 0.45),     # Current: 0.20
    'tp2_close_pct': (0.10, 0.70),     # Current: 0.60
    'tp3_close_pct': (0.05, 0.45),     # Current: 0.10
    'tp4_close_pct': (0.03, 0.30),     # Current: 0.05
    'tp5_close_pct': (0.03, 0.25),     # Current: 0.05
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

        import subprocess
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


def sample_tp_and_sl_params(trial: optuna.Trial, num_tps: int = 5) -> Dict[str, Any]:
    """
    Sample TP R-multiples, close percentages, and SL-after-TP levels.

    TP R-multiples: sampled in strictly increasing order.
    Close percentages: sampled as weights, then normalized to sum to 1.0.
    SL after TP2: between tp1_r and tp2_r (independent)
    SL after TP3: between tp1_r and tp3_r (independent)
    SL after TP4: between tp2_r and tp4_r (independent)
    SL after TP5: between tp3_r and tp5_r (independent)
    SL after TP1: HARDCODED to 0.05R (not sampled)
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

    # ── Close percentages (normalized to sum to 1.0 so full position is closed) ─
    weights = []
    for i in range(1, num_tps + 1):
        key = f'tp{i}_close_pct'
        low, high = TP_CLOSE_RANGES.get(key, (0.05, 0.40))
        w = trial.suggest_float(f'{key}_weight', low, high, step=0.05)
        weights.append(w)

    total = sum(weights)
    for i, w in enumerate(weights, 1):
        params[f'tp{i}_close_pct'] = round(w / total, 3)

    # ── SL levels after each TP hit (each independently optimized) ────────────
    # TP1 → SL = 0.05R HARDCODED (not a trial param)

    # SL after TP2: between tp1_r and tp2_r
    sl2_low = tp1_r
    sl2_high = tp2_r
    if sl2_high - sl2_low < 0.1:
        sl2_high = sl2_low + 0.1
    params['sl_after_tp2_r'] = trial.suggest_float('sl_after_tp2_r', sl2_low, sl2_high, step=0.05)

    # SL after TP3: between tp1_r and tp3_r
    sl3_low = tp1_r
    sl3_high = tp3_r
    if sl3_high - sl3_low < 0.1:
        sl3_high = sl3_low + 0.1
    params['sl_after_tp3_r'] = trial.suggest_float('sl_after_tp3_r', sl3_low, sl3_high, step=0.05)

    # SL after TP4: between tp2_r and tp4_r
    sl4_low = tp2_r
    sl4_high = tp4_r
    if sl4_high - sl4_low < 0.1:
        sl4_high = sl4_low + 0.1
    params['sl_after_tp4_r'] = trial.suggest_float('sl_after_tp4_r', sl4_low, sl4_high, step=0.05)

    # SL after TP5: between tp3_r and tp5_r
    sl5_low = tp3_r
    sl5_high = tp5_r
    if sl5_high - sl5_low < 0.1:
        sl5_high = sl5_low + 0.1
    params['sl_after_tp5_r'] = trial.suggest_float('sl_after_tp5_r', sl5_low, sl5_high, step=0.05)

    return params


def objective(trial: optuna.Trial, start: str, end: str, balance: float, num_tps: int,
              base_params: Dict[str, Any]) -> float:
    """
    Optuna objective function.

    Samples ONLY TP R-multiples, close percentages, and SL-after-TP levels.
    All other params come from base_params (current_params.json).
    Returns a score that Optuna tries to MAXIMIZE.
    """
    # Start from current params (all non-optimized params pass through unchanged)
    params = dict(base_params)

    # Sample and overlay only the TP/SL params
    tp_sl_params = sample_tp_and_sl_params(trial, num_tps)
    params.update(tp_sl_params)

    with _print_lock:
        print(f"\n  Trial {trial.number}: Running backtest...")
        print(f"    TPs: {params.get('tp1_r_multiple', 0):.1f}R / {params.get('tp2_r_multiple', 0):.1f}R / "
              f"{params.get('tp3_r_multiple', 0):.1f}R / {params.get('tp4_r_multiple', 0):.1f}R / "
              f"{params.get('tp5_r_multiple', 0):.1f}R")
        print(f"    Close%: {params.get('tp1_close_pct', 0):.0%} / {params.get('tp2_close_pct', 0):.0%} / "
              f"{params.get('tp3_close_pct', 0):.0%} / {params.get('tp4_close_pct', 0):.0%} / "
              f"{params.get('tp5_close_pct', 0):.0%}")
        print(f"    SL after TP1=0.05R(fixed) | TP2={params.get('sl_after_tp2_r', 0):.2f}R | "
              f"TP3={params.get('sl_after_tp3_r', 0):.2f}R | TP4={params.get('sl_after_tp4_r', 0):.2f}R | "
              f"TP5={params.get('sl_after_tp5_r', 0):.2f}R")

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

    with _print_lock:
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
    """Seed trial 0 with current_params.json TP/SL values."""
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

    # Close percentages as weights — normalize current_params so they sum to 1.0
    raw_close = [base_params.get(f'tp{i}_close_pct', 0.0) for i in range(1, num_tps + 1)]
    total_close = sum(raw_close) or 1.0
    for i, raw in enumerate(raw_close, 1):
        enqueue_params[f'tp{i}_close_pct_weight'] = round(raw / total_close, 4)

    # SL after each TP hit
    tp1_r = tp_r_values[0] if len(tp_r_values) > 0 else 0.6
    tp2_r = tp_r_values[1] if len(tp_r_values) > 1 else 1.1
    tp3_r = tp_r_values[2] if len(tp_r_values) > 2 else 1.8

    enqueue_params['sl_after_tp2_r'] = base_params.get('sl_after_tp2_r', tp1_r)
    enqueue_params['sl_after_tp3_r'] = base_params.get('sl_after_tp3_r', tp1_r)
    enqueue_params['sl_after_tp4_r'] = base_params.get('sl_after_tp4_r', tp2_r)
    enqueue_params['sl_after_tp5_r'] = base_params.get('sl_after_tp5_r', tp3_r)

    if enqueue_params:
        study.enqueue_trial(enqueue_params)


def run_optimization(
    trials: int,
    start: str,
    end: str,
    balance: float = 20000,
    num_tps: int = 5,
    sampler: str = 'tpe',
    output_dir: str = 'backtest/optimization_results',
    n_jobs: int = 1,
    startup_trials: int = 10,
) -> Dict[str, Any]:
    """Run the optimization study."""

    # Load current (non-optimized) params to pass through unchanged
    base_params = load_current_params()

    print("=" * 70)
    print("MAIN LIVE BOT BACKTEST OPTIMIZER - TP/SL LEVELS ONLY")
    print("=" * 70)
    print(f"  Trials: {trials}")
    print(f"  Period: {start} to {end}")
    print(f"  Balance: ${balance:,.0f}")
    print(f"  TP Levels: {num_tps}")
    print(f"  Sampler: {sampler.upper()}")
    print(f"  Parallel Workers: {n_jobs}")
    print("  Optimizing: TP1-TP5 R-multiples, close%, SL after TP2/3/4/5")
    print("  Fixed (from current_params.json): all other params")
    print(f"  SL after TP1: 0.05R (hardcoded, not optimized)")
    print(f"  Random startup trials: {startup_trials}")
    print("=" * 70)

    current_tps = [base_params.get(f'tp{i}_r_multiple', '?') for i in range(1, 6)]
    print(f"  Current TPs: {' / '.join(str(r) for r in current_tps)}")
    print(f"  Current close%: {' / '.join(str(base_params.get(f'tp{i}_close_pct', '?')) for i in range(1, 6))}")
    print("=" * 70)

    if sampler == 'nsga':
        study_sampler = NSGAIISampler(seed=42)
    else:
        study_sampler = TPESampler(seed=42, n_startup_trials=startup_trials)

    study = optuna.create_study(
        direction='maximize',
        sampler=study_sampler,
        study_name=f"tp_sl_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Seed trial 0 with current params
    _enqueue_current_params(study, num_tps, base_params)

    # Run optimization
    study.optimize(
        lambda trial: objective(trial, start, end, balance, num_tps, base_params),
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

    # Reconstruct best TP/SL params from best trial
    best_tp_r = {f'tp{i}_r_multiple': best.params.get(f'tp{i}_r_multiple') for i in range(1, num_tps + 1)}
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
    print(f"    SL after TP1: 0.05R (hardcoded)")
    for sl_key in ['sl_after_tp2_r', 'sl_after_tp3_r', 'sl_after_tp4_r', 'sl_after_tp5_r']:
        print(f"    {sl_key}: {best.params.get(sl_key, '?'):.2f}R")

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

    # All trials summary — sorted by score, showing key trading metrics
    print("\n" + "=" * 80)
    print("ALL TRIALS SUMMARY")
    print("=" * 80)
    print(f"{'#':>3} {'Score':>8} {'Profit%':>8} {'WR%':>6} {'Trades':>7} {'Halts':>6} {'DDD%':>6} {'Valid':>6}")
    print("-" * 80)
    valid_trials = [t for t in study.trials if t.value is not None]
    for t in sorted(valid_trials, key=lambda x: x.value, reverse=True)[:20]:
        score = t.value
        ret = t.user_attrs.get('net_return_pct', 0)
        wr = t.user_attrs.get('win_rate', 0)
        trades = t.user_attrs.get('total_trades', 0)
        halts = t.user_attrs.get('ddd_halts', t.user_attrs.get('safety_events', 0))
        ddd = t.user_attrs.get('max_ddd_pct', 0)
        valid = 'YES' if t.user_attrs.get('valid', False) else 'NO'
        print(f"{t.number:>3} {score:>8.1f} {ret:>+7.1f}% {wr:>5.1f}% {trades:>7} {halts:>6} {ddd:>5.1f}% {valid:>6}")
    print("-" * 80)
    if len(study.trials) > 20:
        print(f"  (Showing top 20 of {len(study.trials)} trials)")

    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {
        "optimization_mode": sampler.upper(),
        "optimization_scope": "TP_SL_LEVELS_ONLY",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": trials,
            "start": start,
            "end": end,
            "balance": balance,
            "num_tps": num_tps,
        },
        "fixed_params": {k: v for k, v in base_params.items()
                         if not k.startswith('tp') and not k.startswith('sl_after_tp')},
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
    print("\n" + "=" * 70)
    print("To apply best parameters to current_params.json, run:")
    print(f"  python backtest/optimize_main_live_bot.py --apply {results_file}")
    print("=" * 70)

    return results


def apply_params(results_file: str):
    """Apply optimized TP/SL parameters to current_params.json."""
    from params.params_loader import load_params_dict

    with open(results_file, 'r') as f:
        results = json.load(f)

    best_params_raw = results.get('best_parameters', {})

    # Reconstruct normalized close percentages from weights
    # Reconstruct normalized close percentages from weights
    weights = [best_params_raw.get(f'tp{i}_close_pct_weight', None) for i in range(1, 6)]
    if any(w is not None for w in weights):
        valid_weights = [w if w is not None else 0.0 for w in weights]
        total_w = sum(valid_weights) or 1.0
        for i, w in enumerate(valid_weights, 1):
            best_params_raw[f'tp{i}_close_pct'] = round(w / total_w, 3)

    # Only apply TP/SL keys (not the weight keys used internally by Optuna)
    apply_keys = {k: v for k, v in best_params_raw.items()
                  if not k.endswith('_weight')}

    # Load current params
    current = load_params_dict()
    if 'parameters' in current:
        current['parameters'].update(apply_keys)
    else:
        current.update(apply_keys)

    current['optimization_mode'] = "OPTIMIZER_TP_SL"
    current['timestamp'] = datetime.now().isoformat()
    current['best_score'] = results.get('best_score', 0)

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    print(f"✅ Applied best TP/SL parameters to {params_file}")
    print("\nApplied parameters:")
    for key, value in sorted(apply_keys.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Optimize TP/SL Levels for Main Live Bot')
    parser.add_argument('--trials', type=int, default=50, help='Number of optimization trials')
    parser.add_argument('--start', type=str, default='2024-01-01', help='Backtest start date')
    parser.add_argument('--end', type=str, default='2024-03-31', help='Backtest end date')
    parser.add_argument('--balance', type=float, default=20000, help='Initial balance')
    parser.add_argument('--num-tps', type=int, default=5, choices=[3, 4, 5], help='Number of TP levels')
    parser.add_argument('--sampler', type=str, default='tpe', choices=['tpe', 'nsga'], help='Optuna sampler')
    parser.add_argument('--output', type=str, default='backtest/optimization_results', help='Output directory')
    parser.add_argument('--apply', type=str, help='Apply parameters from results file')
    parser.add_argument('--parallel', '-j', type=int, default=1, help='Number of parallel workers')
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
