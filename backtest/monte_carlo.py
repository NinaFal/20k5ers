#!/usr/bin/env python3
"""
Monte Carlo Trade Shuffling - Robustness Test

Tests whether results are overfitted/curve-fitted by shuffling the trade
sequence 1000 times and checking if the equity curve stays stable.

Usage:
    # Run backtest first, then Monte Carlo:
    python backtest/monte_carlo.py --start 2015-01-01 --end 2015-05-31 --balance 20000

    # Or use an existing trades.csv:
    python backtest/monte_carlo.py --trades backtest/results/q1_2023/trades.csv --balance 20000

    # More shuffles:
    python backtest/monte_carlo.py --start 2015-01-01 --end 2015-05-31 --balance 20000 --n 2000
"""

import os
import sys
import json
import argparse
import subprocess
import tempfile
import numpy as np
import pandas as pd
from pathlib import Path

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)


def compute_equity_curve(pnls: np.ndarray, initial_balance: float) -> np.ndarray:
    """Build equity curve from list of PnLs."""
    equity = np.empty(len(pnls) + 1)
    equity[0] = initial_balance
    np.cumsum(pnls, out=equity[1:])
    equity[1:] += initial_balance
    return equity


def max_drawdown(equity: np.ndarray) -> float:
    """Max drawdown as fraction of peak equity."""
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak
    return float(dd.max())


def run_backtest(start: str, end: str, balance: float) -> Path:
    """Run main_live_bot_backtest and return path to trades.csv."""
    tmpdir = tempfile.mkdtemp(prefix="mc_backtest_")
    cmd = [
        sys.executable,
        str(Path(current_dir) / "src" / "main_live_bot_backtest.py"),
        "--start", start,
        "--end", end,
        "--balance", str(balance),
        "--output", tmpdir,
    ]
    print(f"▶ Running backtest {start} → {end} (balance: ${balance:,.0f})...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-3000:])
        raise RuntimeError("Backtest failed")

    trades_path = Path(tmpdir) / "trades.csv"
    if not trades_path.exists():
        raise RuntimeError(f"trades.csv not found in {tmpdir}\nSTDOUT: {result.stdout[-2000:]}")

    # Print backtest summary
    results_path = Path(tmpdir) / "results.json"
    if results_path.exists():
        with open(results_path) as f:
            r = json.load(f)
        final = r.get("final_balance", balance)
        ret = (final - balance) / balance * 100
        print(f"   Backtest result: ${final:,.2f} ({ret:+.1f}%) | Trades: ", end="")

    return trades_path


def monte_carlo(pnls: np.ndarray, initial_balance: float, n: int = 1000, seed: int = 42):
    """
    Shuffle trade sequence n times and collect statistics.

    Returns dict with:
        final_returns  : array of final return % per shuffle
        max_drawdowns  : array of max drawdown % per shuffle
        equity_curves  : array (n x len(pnls)+1) of equity curves
    """
    rng = np.random.default_rng(seed)
    n_trades = len(pnls)
    equity_curves = np.empty((n, n_trades + 1))
    max_drawdowns_arr = np.empty(n)

    for i in range(n):
        shuffled = rng.permutation(pnls)
        eq = compute_equity_curve(shuffled, initial_balance)
        equity_curves[i] = eq
        max_drawdowns_arr[i] = max_drawdown(eq)

    final_balances = equity_curves[:, -1]
    final_returns = (final_balances - initial_balance) / initial_balance * 100

    return {
        "final_returns": final_returns,
        "max_drawdowns": max_drawdowns_arr * 100,
        "equity_curves": equity_curves,
    }


def print_report(stats: dict, pnls: np.ndarray, initial_balance: float, n: int):
    dd = stats["max_drawdowns"]
    eq_curves = stats["equity_curves"]

    original_eq = compute_equity_curve(pnls, initial_balance)
    original_ret = (original_eq[-1] - initial_balance) / initial_balance * 100
    original_dd = max_drawdown(original_eq) * 100
    # Fixed final return (sum doesn't change with shuffle)
    fixed_ret = original_ret

    # Drawdown-based robustness
    pct_dd_ok = np.mean(dd <= 10) * 100       # DD within 5ers challenge limit
    pct_dd_halt = np.mean(dd > 10) * 100      # Challenge-halting DD
    pct_dd_severe = np.mean(dd > 15) * 100    # Very bad

    # Minimum equity per shuffle (path risk)
    min_equity_per_shuffle = eq_curves.min(axis=1)
    min_eq_pct = (min_equity_per_shuffle - initial_balance) / initial_balance * 100
    pct_never_below_start = np.mean(min_equity_per_shuffle >= initial_balance) * 100

    # % of time equity curve is above watermark (time-in-profit)
    above_start = (eq_curves >= initial_balance).mean(axis=1) * 100  # per shuffle
    median_time_in_profit = np.median(above_start)

    # Consecutive loss exposure: max consecutive losses per shuffle
    loses = (pnls < 0).astype(int)
    # Count max consecutive losses in original
    max_consec = 0
    cur = 0
    for l in loses:
        cur = cur + 1 if l else 0
        max_consec = max(max_consec, cur)

    sep = "─" * 60
    print(f"\n{'═' * 60}")
    print(f"  MONTE CARLO TRADE SHUFFLING  ({n:,} simulaties)")
    print(f"{'═' * 60}")
    print(f"  Originele volgorde:")
    print(f"    Return:            {original_ret:+.1f}%  (vast — som verandert niet)")
    print(f"    Max Drawdown:      {original_dd:.2f}%")
    print(f"    Trades:            {len(pnls)}")
    print(f"    Max consec. losses: {max_consec}")
    print(f"    Win rate:          {np.mean(pnls > 0)*100:.1f}%")
    print(f"{sep}")
    print(f"  ⚠️  NOTE: Finale return = altijd {fixed_ret:+.1f}% (ongeacht volgorde)")
    print(f"      Monte Carlo test → PAD-stabiliteit & drawdown-risico")
    print(f"{sep}")
    print(f"  Drawdown distributie (1000 shuffle-paden):")
    print(f"    Mediaan DD:        {np.median(dd):.2f}%")
    print(f"    25e percentiel:    {np.percentile(dd, 25):.2f}%")
    print(f"    75e percentiel:    {np.percentile(dd, 75):.2f}%")
    print(f"    95e percentiel:    {np.percentile(dd, 95):.2f}%  (worst 5%)")
    print(f"    Max DD ooit:       {dd.max():.2f}%")
    print(f"{sep}")
    print(f"  Pad-robuustheid:")
    print(f"    % paden DD ≤ 10%:  {pct_dd_ok:.1f}%   (5ers challenge veilig)")
    print(f"    % paden DD > 10%:  {pct_dd_halt:.1f}%   (challenge halt risico)")
    print(f"    % paden DD > 15%:  {pct_dd_severe:.1f}%   (ernstig)")
    print(f"    % paden boven start: {pct_never_below_start:.1f}%  (nooit onder startkapitaal)")
    print(f"    Mediaan diepste dip: {np.median(min_eq_pct):+.1f}%  (diepste punt mediaan pad)")
    print(f"    5e pct diepste dip:  {np.percentile(min_eq_pct, 5):+.1f}%  (worst 5% pad)")
    print(f"    Mediaan tijd in winst: {median_time_in_profit:.0f}%  (van de handelstijd)")
    print(f"{'═' * 60}")

    # Verdict
    print(f"\n  OORDEEL:")
    issues = []
    if pct_dd_ok < 50:
        issues.append(f"⚠️  Slechts {pct_dd_ok:.0f}% van paden houdt DD ≤ 10% — hoog halt-risico")
    if np.percentile(dd, 95) > 12:
        issues.append(f"⚠️  95e pct DD = {np.percentile(dd,95):.1f}% — in 5% scenario's challenge halt")
    if np.percentile(min_eq_pct, 5) < -12:
        issues.append(f"⚠️  Diepste dip (worst 5%) = {np.percentile(min_eq_pct,5):.1f}% — groot verliesrisico")
    if median_time_in_profit < 50:
        issues.append(f"⚠️  Mediaan {median_time_in_profit:.0f}% van de tijd boven water — onstabiel pad")

    if not issues:
        print(f"  ✅ ROBUUST — pad stabiel over {n:,} shuffles")
        print(f"     {pct_dd_ok:.0f}% van paden DD ≤ 10% | Mediaan DD {np.median(dd):.1f}% | "
              f"95e pct DD {np.percentile(dd,95):.1f}%")
    else:
        print(f"  🔴 AANDACHTSPUNTEN:")
        for issue in issues:
            print(f"     {issue}")
    print(f"{'═' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description="Monte Carlo Trade Shuffling")
    parser.add_argument("--trades", type=str, help="Pad naar trades.csv (skip backtest)")
    parser.add_argument("--start", type=str, help="Backtest start datum (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="Backtest eind datum (YYYY-MM-DD)")
    parser.add_argument("--balance", type=float, default=20000, help="Startkapitaal (default: 20000)")
    parser.add_argument("--n", type=int, default=1000, help="Aantal shuffles (default: 1000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    if args.trades:
        trades_path = Path(args.trades)
        if not trades_path.exists():
            print(f"❌ trades.csv niet gevonden: {trades_path}")
            sys.exit(1)
    elif args.start and args.end:
        trades_path = run_backtest(args.start, args.end, args.balance)
    else:
        parser.print_help()
        sys.exit(1)

    df = pd.read_csv(trades_path)
    if "pnl" not in df.columns:
        print(f"❌ Geen 'pnl' kolom in {trades_path}. Kolommen: {list(df.columns)}")
        sys.exit(1)

    pnls = df["pnl"].values.astype(float)
    print(f"{len(pnls)} trades geladen uit {trades_path}")

    if len(pnls) < 10:
        print("⚠️  Te weinig trades voor betrouwbare Monte Carlo (min 10)")
        sys.exit(1)

    print(f"▶ Monte Carlo: {args.n:,} shuffles...", flush=True)
    stats = monte_carlo(pnls, args.balance, n=args.n, seed=args.seed)
    print_report(stats, pnls, args.balance, args.n)


if __name__ == "__main__":
    main()
