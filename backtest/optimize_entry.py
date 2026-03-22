#!/usr/bin/env python3
"""
Entry-Only Optimizer — Same signals, better entry prices.

Optimizes ONLY entry_fib_level and entry_limit_offset_atr while keeping
all other parameters fixed at their current values.

Each trial runs 3 backtest periods and combines the scores:
  - Jan 2015 – May 2015
  - Jan 2016 – May 2016
  - Nov 2019 – Mar 2020

Usage:
    python backtest/optimize_entry.py --trials 70 -j 4
    python backtest/optimize_entry.py --trials 50 --start 2024-01-01 --end 2024-12-31
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

# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-PERIOD CONFIG — 3 periods evaluated per trial
# ═══════════════════════════════════════════════════════════════════════════════
MULTI_PERIODS = [
    ("2015-01-01", "2015-05-31", "Jan–May 2015"),
    ("2016-01-01", "2016-05-31", "Jan–May 2016"),
    ("2019-11-01", "2020-03-31", "Nov 2019–Mar 2020"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT SYMBOLS — All live bot symbols with data from 2015+
# Excludes: NZD_JPY (user request), SPX500_USD (no 2015 data),
#           UK100_USD (no 2015 data), crypto (no 2015 data),
#           XBR_USD/XTI_USD oil (no 2015 data)
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_SYMBOLS = [
    # Forex majors
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
    # EUR crosses
    "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_AUD", "EUR_CAD", "EUR_NZD",
    # GBP crosses
    "GBP_JPY", "GBP_CHF", "GBP_AUD", "GBP_CAD", "GBP_NZD",
    # Other crosses
    "AUD_JPY", "AUD_CHF", "AUD_CAD", "AUD_NZD",
    "NZD_CHF", "NZD_CAD", "CAD_JPY", "CAD_CHF", "CHF_JPY",
    # Metals
    "XAU_USD", "XAG_USD",
    # Indices (NAS100 has 2015 data; UK100 does not)
    "NAS100_USD",
]


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


def run_backtest(params: Dict[str, Any], start: str, end: str, balance: float,
                 symbols: str = None) -> Result:
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
        symbols_str = symbols or ",".join(DEFAULT_SYMBOLS)
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "src" / "main_live_bot_backtest.py"),
            "--start", start,
            "--end", end,
            "--balance", str(balance),
            "--output", str(output_dir),
            "--params-file", str(temp_file),
            "--symbols", symbols_str,
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


def score_result(result: Result) -> float:
    """Score a single backtest result."""
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


def objective(trial: optuna.Trial, base_params: Dict[str, Any],
              start: str, end: str, balance: float, symbols: str = None,
              multi_period: bool = False) -> float:
    """Optimize ONLY entry parameters. Everything else is fixed."""
    params = base_params.copy()

    params['entry_fib_level'] = trial.suggest_float(
        'entry_fib_level', ENTRY_FIB_RANGE[0], ENTRY_FIB_RANGE[1], step=0.001
    )
    params['entry_limit_offset_atr'] = trial.suggest_float(
        'entry_limit_offset_atr', ENTRY_OFFSET_ATR_RANGE[0], ENTRY_OFFSET_ATR_RANGE[1], step=0.02
    )

    fib = params['entry_fib_level']
    offset = params['entry_limit_offset_atr']
    print(f"\n  Trial {trial.number}: fib={fib:.3f}, offset={offset:.2f}×ATR", flush=True)

    if multi_period:
        # === MULTI-PERIOD: run 3 periods, average the scores ===
        period_scores = []
        total_trades = 0
        win_rates = []
        max_tdd = 0.0
        max_ddd = 0.0
        total_ddd_halts = 0
        all_valid = True

        for p_start, p_end, p_label in MULTI_PERIODS:
            result = run_backtest(params, p_start, p_end, balance, symbols)
            ps = score_result(result)
            period_scores.append(ps)
            total_trades += result.total_trades
            if result.total_trades > 0:
                win_rates.append(result.win_rate)
            max_tdd = max(max_tdd, result.max_tdd_pct)
            max_ddd = max(max_ddd, result.max_ddd_pct)
            total_ddd_halts += result.ddd_halts
            if not result.valid:
                all_valid = False
            print(f"    [{p_label}] Return: {result.net_return_pct:+.1f}%, "
                  f"Trades: {result.total_trades}, WR: {result.win_rate:.1f}%, "
                  f"TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%", flush=True)

        avg_score = sum(period_scores) / len(period_scores)
        avg_wr = sum(win_rates) / len(win_rates) if win_rates else 0.0

        trial.set_user_attr('net_return_pct', avg_score)
        trial.set_user_attr('total_trades', total_trades)
        trial.set_user_attr('win_rate', avg_wr)
        trial.set_user_attr('max_tdd_pct', max_tdd)
        trial.set_user_attr('max_ddd_pct', max_ddd)
        trial.set_user_attr('ddd_halts', total_ddd_halts)
        trial.set_user_attr('valid', all_valid)
        trial.set_user_attr('period_scores', period_scores)

        print(f"    => COMBINED score: {avg_score:.2f} (periods: "
              f"{', '.join(f'{s:.1f}' for s in period_scores)})", flush=True)
        return avg_score

    else:
        # === SINGLE-PERIOD (legacy) ===
        result = run_backtest(params, start, end, balance, symbols)

        trial.set_user_attr('net_return_pct', result.net_return_pct)
        trial.set_user_attr('total_trades', result.total_trades)
        trial.set_user_attr('win_rate', result.win_rate)
        trial.set_user_attr('max_tdd_pct', result.max_tdd_pct)
        trial.set_user_attr('max_ddd_pct', result.max_ddd_pct)
        trial.set_user_attr('ddd_halts', result.ddd_halts)
        trial.set_user_attr('valid', result.valid)

        print(f"    -> Return: {result.net_return_pct:+.1f}%, Trades: {result.total_trades}, "
              f"Win: {result.win_rate:.1f}%, TDD: {result.max_tdd_pct:.2f}%, DDD: {result.max_ddd_pct:.2f}%",
              flush=True)

        return score_result(result)


def main():
    parser = argparse.ArgumentParser(description='Entry-Only Optimizer')
    parser.add_argument('--trials', type=int, default=70,
        help='Total trials (default: 70 = 20 startup + 50 TPE)')
    parser.add_argument('--startup-trials', type=int, default=20,
        help='Random startup trials before TPE kicks in (default: 20)')
    parser.add_argument('--start', type=str, default='2024-01-01',
        help='Ignored in multi-period mode')
    parser.add_argument('--end', type=str, default='2024-12-31',
        help='Ignored in multi-period mode')
    parser.add_argument('--balance', type=float, default=20000)
    parser.add_argument('--parallel', '-j', type=int, default=4)
    parser.add_argument('--symbols', type=str, default=None,
        help='Comma-separated symbols. Default: 30 symbols with 2015+ data')
    parser.add_argument('--multi-period', action='store_true', default=True,
        help='Run 3 periods per trial: Jan-May 2015, Jan-May 2016, Nov2019-Mar2020 (default: ON)')
    parser.add_argument('--single-period', dest='multi_period', action='store_false',
        help='Use single --start/--end period instead of multi-period')
    parser.add_argument('--apply', type=str, help='Apply results file to current_params.json')
    args = parser.parse_args()

    if args.apply:
        apply_params(args.apply)
        return

    base_params = load_base_params()

    print("=" * 70)
    print("ENTRY-ONLY OPTIMIZER — MULTI-PERIOD" if args.multi_period else "ENTRY-ONLY OPTIMIZER")
    print("=" * 70)
    print(f"  Trials:         {args.trials} total ({args.startup_trials} startup + "
          f"{args.trials - args.startup_trials} TPE)")
    print(f"  Workers:        {args.parallel}")
    print(f"  Balance:        ${args.balance:,.0f} per period")
    if args.multi_period:
        print(f"  Periods (x3 per trial):")
        for p_start, p_end, p_label in MULTI_PERIODS:
            print(f"    • {p_label}  ({p_start} – {p_end})")
    else:
        print(f"  Period:         {args.start} to {args.end}")
    symbols_str = args.symbols or ",".join(DEFAULT_SYMBOLS)
    symbol_list = symbols_str.split(",")
    print(f"  Fib range:      {ENTRY_FIB_RANGE[0]} – {ENTRY_FIB_RANGE[1]}")
    print(f"  Offset range:   {ENTRY_OFFSET_ATR_RANGE[0]} – {ENTRY_OFFSET_ATR_RANGE[1]} ATR")
    print(f"  Baseline:       fib={base_params.get('entry_fib_level', 0.618):.3f}, "
          f"offset={base_params.get('entry_limit_offset_atr', 0.0):.2f}")
    print(f"  Symbols:        {len(symbol_list)} ({', '.join(symbol_list[:5])}...)")
    print("  ALL other params: FIXED at current values")
    print("=" * 70)

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction='maximize',
        sampler=TPESampler(n_startup_trials=args.startup_trials, seed=42),
        study_name=f"entry_multi_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    # Seed trial 0 with current baseline
    study.enqueue_trial({
        'entry_fib_level': base_params.get('entry_fib_level', 0.618),
        'entry_limit_offset_atr': base_params.get('entry_limit_offset_atr', 0.0),
    })

    study.optimize(
        lambda trial: objective(
            trial, base_params, args.start, args.end, args.balance,
            symbols_str, multi_period=args.multi_period
        ),
        n_trials=args.trials,
        n_jobs=args.parallel,
        show_progress_bar=False,
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
        b_score = baseline.value or 0
        b_wr = baseline.user_attrs.get('win_rate', 0)
        best_score = best.value or 0
        best_wr = best.user_attrs.get('win_rate', 0)
        print(f"\n  BASELINE (fib={baseline.params.get('entry_fib_level', 0.618):.3f}, "
              f"offset={baseline.params.get('entry_limit_offset_atr', 0.0):.2f}):  "
              f"score={b_score:.2f}, WR={b_wr:.1f}%")
        print(f"  BEST ENTRY:   score={best_score:.2f}, WR={best_wr:.1f}%")
        print(f"  IMPROVEMENT:  {best_score - b_score:+.2f} score")

    # All trials table
    print("\n" + "=" * 80)
    print("ALL TRIALS")
    print("=" * 80)
    if args.multi_period:
        print(f"{'#':>3} {'Score':>8} {'Fib':>6} {'Offset':>7} {'Trades':>7} {'WR%':>6} "
              f"{'MaxTDD':>7} {'MaxDDD':>7} {'P1':>7} {'P2':>7} {'P3':>7}")
        print("-" * 80)
        for t in sorted(study.trials, key=lambda x: x.value if x.value is not None else -999, reverse=True):
            s = t.value if t.value is not None else -999
            fib = t.params.get('entry_fib_level', 0)
            off = t.params.get('entry_limit_offset_atr', 0)
            trades = t.user_attrs.get('total_trades', 0)
            wr = t.user_attrs.get('win_rate', 0)
            tdd = t.user_attrs.get('max_tdd_pct', 0)
            ddd = t.user_attrs.get('max_ddd_pct', 0)
            ps = t.user_attrs.get('period_scores', [0, 0, 0])
            p1, p2, p3 = (ps + [0, 0, 0])[:3]
            marker = " <--" if t.number == 0 else ""
            print(f"{t.number:>3} {s:>8.1f} {fib:>6.3f} {off:>6.2f}x {trades:>7} {wr:>5.1f}% "
                  f"{tdd:>6.1f}% {ddd:>6.1f}% {p1:>7.1f} {p2:>7.1f} {p3:>7.1f}{marker}")
    else:
        print(f"{'#':>3} {'Score':>8} {'Fib':>6} {'Offset':>7} {'Return':>8} {'Trades':>7} {'WR%':>6} {'TDD':>6} {'DDD':>6}")
        print("-" * 80)
        for t in sorted(study.trials, key=lambda x: x.value if x.value is not None else -999, reverse=True):
            s = t.value if t.value is not None else -999
            fib = t.params.get('entry_fib_level', 0)
            off = t.params.get('entry_limit_offset_atr', 0)
            ret = t.user_attrs.get('net_return_pct', 0)
            trades = t.user_attrs.get('total_trades', 0)
            wr = t.user_attrs.get('win_rate', 0)
            tdd = t.user_attrs.get('max_tdd_pct', 0)
            ddd = t.user_attrs.get('max_ddd_pct', 0)
            marker = " <-- baseline" if t.number == 0 else ""
            print(f"{t.number:>3} {s:>8.1f} {fib:>6.3f} {off:>6.2f}x {ret:>+7.1f}% {trades:>7} {wr:>5.1f}% {tdd:>5.1f}% {ddd:>5.1f}%{marker}")
    print("-" * 80)

    # Save results
    output_dir = Path('backtest/optimization_results')
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "optimization_mode": "ENTRY_MULTI_PERIOD" if args.multi_period else "ENTRY_ONLY",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "trials": args.trials,
            "startup_trials": args.startup_trials,
            "multi_period": args.multi_period,
            "periods": [{"start": s, "end": e, "label": l} for s, e, l in MULTI_PERIODS] if args.multi_period else None,
            "start": args.start,
            "end": args.end,
            "balance": args.balance,
            "workers": args.parallel,
            "symbols": symbol_list,
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
