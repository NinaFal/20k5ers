#!/usr/bin/env python3
"""
Comprehensive Backtest Report Generator

Generates full analysis from backtest results:
- Total summary (profit $, %, winrate, tradecount, halts)
- Per-month breakdown
- Per-asset breakdown
- All trades exported to CSV

Usage:
    python backtest/generate_backtest_report.py --results-dir ftmo_analysis_output/backtest_2015_2025
"""

import json
import csv
import sys
import os
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def load_results(results_dir: Path):
    """Load results.json and trades.csv from the backtest output directory."""
    results_file = results_dir / "results.json"
    trades_file = results_dir / "trades.csv"

    if not results_file.exists():
        print(f"ERROR: {results_file} not found. Backtest may still be running.")
        sys.exit(1)

    with open(results_file) as f:
        results = json.load(f)

    trades = []
    if trades_file.exists():
        with open(trades_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['pnl'] = float(row['pnl'])
                row['volume'] = float(row['volume'])
                row['open_price'] = float(row['open_price'])
                row['close_price'] = float(row['close_price'])
                row['partial'] = row.get('partial', 'False') == 'True'
                trades.append(row)

    return results, trades


def format_currency(value):
    """Format as currency with sign."""
    if value >= 0:
        return f"+${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_pct(value):
    """Format as percentage with sign."""
    if value >= 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def generate_total_summary(results, trades, report_lines):
    """Generate the total backtest summary section."""
    report_lines.append("=" * 80)
    report_lines.append("FULL BACKTEST REPORT: 2015 - 2025")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Account summary
    report_lines.append("╔══════════════════════════════════════════════════════════════╗")
    report_lines.append("║                    ACCOUNT SUMMARY                           ║")
    report_lines.append("╠══════════════════════════════════════════════════════════════╣")
    report_lines.append(f"║  Initial Balance:    ${results['initial_balance']:>12,.2f}                    ║")
    report_lines.append(f"║  Final Balance:      ${results['final_balance']:>12,.2f}                    ║")
    report_lines.append(f"║  Net Profit ($):     {format_currency(results['net_pnl']):>13}                    ║")
    report_lines.append(f"║  Net Profit (%):     {format_pct(results['return_pct']):>13}                    ║")
    report_lines.append("╠══════════════════════════════════════════════════════════════╣")
    report_lines.append("║                    TRADE STATISTICS                          ║")
    report_lines.append("╠══════════════════════════════════════════════════════════════╣")
    report_lines.append(f"║  Total Trades:       {results['total_trades']:>8}                              ║")
    report_lines.append(f"║  Winners:            {results['winners']:>8}                              ║")
    report_lines.append(f"║  Losers:             {results['losers']:>8}                              ║")
    report_lines.append(f"║  Win Rate:           {results['win_rate']:>7.1f}%                              ║")

    # Calculate additional stats from trades
    full_trades = [t for t in trades if not t['partial']]
    winning_trades = [t for t in full_trades if t['pnl'] > 0]
    losing_trades = [t for t in full_trades if t['pnl'] <= 0]

    avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
    profit_factor = abs(sum(t['pnl'] for t in winning_trades) / sum(t['pnl'] for t in losing_trades)) if losing_trades and sum(t['pnl'] for t in losing_trades) != 0 else float('inf')

    report_lines.append(f"║  Avg Win ($):        {format_currency(avg_win):>13}                    ║")
    report_lines.append(f"║  Avg Loss ($):       {format_currency(avg_loss):>13}                    ║")
    report_lines.append(f"║  Profit Factor:      {profit_factor:>8.2f}                              ║")
    report_lines.append("╠══════════════════════════════════════════════════════════════╣")
    report_lines.append("║                    RISK & SAFETY                             ║")
    report_lines.append("╠══════════════════════════════════════════════════════════════╣")
    report_lines.append(f"║  Max TDD:            {results['max_tdd_pct']:>7.2f}%  (limit 10%)               ║")
    report_lines.append(f"║  Max DDD:            {results['max_ddd_pct']:>7.2f}%  (limit 5%)                ║")
    report_lines.append(f"║  DDD Warnings:       {results.get('ddd_warnings', 0):>8}                              ║")
    report_lines.append(f"║  DDD Reduces:        {results.get('ddd_reduces', 0):>8}                              ║")
    report_lines.append(f"║  DDD Halts:          {results.get('ddd_halts', 0):>8}                              ║")
    report_lines.append(f"║  TDD Stop-outs:      {results.get('tdd_stopouts', 0):>8}                              ║")
    report_lines.append(f"║  Total Safety Events:{results.get('safety_events', 0):>8}                              ║")
    report_lines.append("╚══════════════════════════════════════════════════════════════╝")
    report_lines.append("")


def generate_monthly_report(results, trades, report_lines):
    """Generate per-month breakdown."""
    monthly = results.get('monthly_stats', {})
    if not monthly:
        report_lines.append("No monthly data available.")
        return

    report_lines.append("=" * 80)
    report_lines.append("PER-MONTH BREAKDOWN")
    report_lines.append("=" * 80)
    report_lines.append("")

    header = f"{'Month':<10} {'Trades':>7} {'Win':>5} {'Loss':>5} {'WR%':>7} {'PnL ($)':>14} {'Partials':>9}"
    report_lines.append(header)
    report_lines.append("-" * len(header))

    # Sort months chronologically
    sorted_months = sorted(monthly.keys())

    yearly_stats = defaultdict(lambda: {'trades': 0, 'winners': 0, 'losers': 0, 'pnl': 0.0, 'partials': 0})

    for month_key in sorted_months:
        stats = monthly[month_key]
        year = month_key[:4]
        yearly_stats[year]['trades'] += stats['trades']
        yearly_stats[year]['winners'] += stats['winners']
        yearly_stats[year]['losers'] += stats['losers']
        yearly_stats[year]['pnl'] += stats['pnl']
        yearly_stats[year]['partials'] += stats.get('partial_closes', 0)

        wr = stats['win_rate'] if stats.get('win_rate') else (stats['winners'] / stats['trades'] * 100 if stats['trades'] > 0 else 0)
        report_lines.append(
            f"{month_key:<10} {stats['trades']:>7} {stats['winners']:>5} {stats['losers']:>5} "
            f"{wr:>6.1f}% {format_currency(stats['pnl']):>14} {stats.get('partial_closes', 0):>9}"
        )

        # Add yearly subtotal after December or last month of a year
        next_idx = sorted_months.index(month_key) + 1
        next_year = sorted_months[next_idx][:4] if next_idx < len(sorted_months) else None
        if next_year != year:
            ys = yearly_stats[year]
            yr_wr = ys['winners'] / ys['trades'] * 100 if ys['trades'] > 0 else 0
            report_lines.append("-" * len(header))
            report_lines.append(
                f"{year + ' TOTAL':<10} {ys['trades']:>7} {ys['winners']:>5} {ys['losers']:>5} "
                f"{yr_wr:>6.1f}% {format_currency(ys['pnl']):>14} {ys['partials']:>9}"
            )
            report_lines.append("=" * len(header))

    report_lines.append("")

    # Yearly summary table
    report_lines.append("-" * 80)
    report_lines.append("YEARLY SUMMARY")
    report_lines.append("-" * 80)
    header2 = f"{'Year':<8} {'Trades':>7} {'Win':>5} {'Loss':>5} {'WR%':>7} {'PnL ($)':>14} {'Avg/Trade':>12}"
    report_lines.append(header2)
    report_lines.append("-" * len(header2))

    for year in sorted(yearly_stats.keys()):
        ys = yearly_stats[year]
        yr_wr = ys['winners'] / ys['trades'] * 100 if ys['trades'] > 0 else 0
        avg_trade = ys['pnl'] / ys['trades'] if ys['trades'] > 0 else 0
        report_lines.append(
            f"{year:<8} {ys['trades']:>7} {ys['winners']:>5} {ys['losers']:>5} "
            f"{yr_wr:>6.1f}% {format_currency(ys['pnl']):>14} {format_currency(avg_trade):>12}"
        )

    report_lines.append("")


def generate_per_asset_report(trades, report_lines):
    """Generate per-asset breakdown from trades."""
    report_lines.append("=" * 80)
    report_lines.append("PER-ASSET BREAKDOWN")
    report_lines.append("=" * 80)
    report_lines.append("")

    # Group trades by symbol (only full trades for win/loss stats)
    asset_stats = defaultdict(lambda: {
        'trades': 0, 'winners': 0, 'losers': 0, 'pnl': 0.0,
        'total_pnl_with_partials': 0.0, 'partials': 0
    })

    for trade in trades:
        symbol = trade['symbol']
        pnl = trade['pnl']

        asset_stats[symbol]['total_pnl_with_partials'] += pnl

        if trade['partial']:
            asset_stats[symbol]['partials'] += 1
        else:
            asset_stats[symbol]['trades'] += 1
            if pnl > 0:
                asset_stats[symbol]['winners'] += 1
            else:
                asset_stats[symbol]['losers'] += 1
            asset_stats[symbol]['pnl'] += pnl

    # Sort by total PnL (including partials) descending
    sorted_assets = sorted(asset_stats.items(), key=lambda x: x[1]['total_pnl_with_partials'], reverse=True)

    header = f"{'Symbol':<16} {'Trades':>7} {'Win':>5} {'Loss':>5} {'WR%':>7} {'PnL ($)':>14} {'Partials':>9}"
    report_lines.append(header)
    report_lines.append("-" * len(header))

    total_trades = 0
    total_winners = 0
    total_losers = 0
    total_pnl = 0.0
    total_partials = 0

    for symbol, stats in sorted_assets:
        wr = stats['winners'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        report_lines.append(
            f"{symbol:<16} {stats['trades']:>7} {stats['winners']:>5} {stats['losers']:>5} "
            f"{wr:>6.1f}% {format_currency(stats['total_pnl_with_partials']):>14} {stats['partials']:>9}"
        )
        total_trades += stats['trades']
        total_winners += stats['winners']
        total_losers += stats['losers']
        total_pnl += stats['total_pnl_with_partials']
        total_partials += stats['partials']

    report_lines.append("-" * len(header))
    total_wr = total_winners / total_trades * 100 if total_trades > 0 else 0
    report_lines.append(
        f"{'TOTAL':<16} {total_trades:>7} {total_winners:>5} {total_losers:>5} "
        f"{total_wr:>6.1f}% {format_currency(total_pnl):>14} {total_partials:>9}"
    )
    report_lines.append("")

    # Top 5 best and worst assets
    report_lines.append("-" * 80)
    report_lines.append("TOP 5 BEST PERFORMING ASSETS:")
    for symbol, stats in sorted_assets[:5]:
        wr = stats['winners'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        report_lines.append(f"  {symbol:<16} {format_currency(stats['total_pnl_with_partials']):>14}  (WR: {wr:.1f}%, {stats['trades']} trades)")

    report_lines.append("")
    report_lines.append("TOP 5 WORST PERFORMING ASSETS:")
    for symbol, stats in sorted_assets[-5:]:
        wr = stats['winners'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        report_lines.append(f"  {symbol:<16} {format_currency(stats['total_pnl_with_partials']):>14}  (WR: {wr:.1f}%, {stats['trades']} trades)")

    report_lines.append("")


def generate_all_trades_csv(trades, output_dir):
    """Export all trades to a clean CSV for analysis."""
    output_file = output_dir / "all_trades_analysis.csv"

    # Enrich trades with computed fields
    enriched = []
    for t in trades:
        row = {
            'ticket': t.get('ticket', ''),
            'symbol': t['symbol'],
            'type': t['type'],
            'volume': t['volume'],
            'open_price': t['open_price'],
            'close_price': t['close_price'],
            'open_time': t['open_time'],
            'close_time': t['close_time'],
            'pnl': t['pnl'],
            'sl': t.get('sl', ''),
            'tp': t.get('tp', ''),
            'is_partial': t['partial'],
        }

        # Parse dates for duration
        try:
            open_dt = datetime.fromisoformat(str(t['open_time']))
            close_dt = datetime.fromisoformat(str(t['close_time']))
            duration_hours = (close_dt - open_dt).total_seconds() / 3600
            row['duration_hours'] = round(duration_hours, 1)
            row['month'] = open_dt.strftime('%Y-%m')
            row['year'] = open_dt.strftime('%Y')
            row['day_of_week'] = open_dt.strftime('%A')
        except (ValueError, TypeError):
            row['duration_hours'] = ''
            row['month'] = ''
            row['year'] = ''
            row['day_of_week'] = ''

        row['result'] = 'WIN' if t['pnl'] > 0 else 'LOSS'
        enriched.append(row)

    if enriched:
        fieldnames = list(enriched[0].keys())
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched)

    return output_file


def main():
    parser = argparse.ArgumentParser(description='Generate comprehensive backtest report')
    parser.add_argument('--results-dir', type=str, default='ftmo_analysis_output/backtest_2015_2025',
                        help='Directory containing results.json and trades.csv')
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    print(f"Loading results from {results_dir}...")
    results, trades = load_results(results_dir)
    print(f"Loaded {len(trades)} trade records")

    report_lines = []

    # 1. Total summary
    generate_total_summary(results, trades, report_lines)

    # 2. Monthly breakdown
    generate_monthly_report(results, trades, report_lines)

    # 3. Per-asset breakdown
    generate_per_asset_report(trades, report_lines)

    # 4. All trades CSV
    trades_file = generate_all_trades_csv(trades, results_dir)
    report_lines.append(f"All trades exported to: {trades_file}")
    report_lines.append("")

    # Write report
    report_text = "\n".join(report_lines)
    report_file = results_dir / "FULL_REPORT.txt"
    with open(report_file, 'w') as f:
        f.write(report_text)

    # Also print to stdout
    print(report_text)
    print(f"\nReport saved to: {report_file}")
    print(f"All trades CSV: {trades_file}")


if __name__ == "__main__":
    main()
