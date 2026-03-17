"""Comprehensive backtest analysis script - 2015-2025"""
import pandas as pd
import json
from collections import defaultdict

# Load data
trades = pd.read_csv('ftmo_analysis_output/backtest_2015_2025/trades.csv')
with open('ftmo_analysis_output/backtest_2015_2025/results.json') as f:
    results = json.load(f)

# Parse times
trades['open_time'] = pd.to_datetime(trades['open_time'])
trades['close_time'] = pd.to_datetime(trades['close_time'])
trades['year'] = trades['close_time'].dt.year

# Separate full trades vs partial closes
full_trades = trades[trades['partial'] != True].copy()
partial_trades = trades[trades['partial'] == True].copy()

# For per-asset stats, aggregate ALL trades (partials + full closes) per original ticket
# Group by base ticket (strip partial suffix)
trades['base_ticket'] = trades['ticket'].astype(str).str.extract(r'^(\d+)')[0].astype(int)

# Aggregate PnL by base ticket and symbol
trade_groups = trades.groupby(['base_ticket', 'symbol']).agg(
    total_pnl=('pnl', 'sum'),
    close_time=('close_time', 'max'),
    open_time=('open_time', 'min'),
    num_closes=('pnl', 'count')
).reset_index()
trade_groups['year'] = trade_groups['close_time'].dt.year
trade_groups['month'] = trade_groups['close_time'].dt.to_period('M')
trade_groups['winner'] = trade_groups['total_pnl'] > 0

print("=" * 100)
print("COMPREHENSIVE BACKTEST REPORT: 2015-2025")
print("=" * 100)
print(f"\nPeriod: 2015-01-01 to 2025-12-31")
print(f"Initial Balance: $20,000")
print(f"Final Balance: ${results['final_balance']:,.2f}")
print(f"Net PnL: ${results['net_pnl']:,.2f}")
print(f"Return: {results['return_pct']:,.1f}%")
print(f"\nTotal Trades: {len(trade_groups)}")
print(f"Winners: {trade_groups['winner'].sum()} ({trade_groups['winner'].mean()*100:.1f}%)")
print(f"Losers: {(~trade_groups['winner']).sum()}")
print(f"Max DDD: {results['max_ddd_pct']:.2f}%")
print(f"DDD Halts: {results['ddd_halts']}")
print(f"DDD Reduces: {results['ddd_reduces']}")
print(f"DDD Warnings: {results['ddd_warnings']}")

# ============================================================
# PER-YEAR SUMMARY
# ============================================================
print("\n" + "=" * 100)
print("YEARLY SUMMARY")
print("=" * 100)
print(f"{'Year':<8} {'Trades':>8} {'Winners':>8} {'WR%':>8} {'PnL':>18} {'Losing Months':>15}")
print("-" * 70)

monthly = results['monthly_stats']
for year in range(2015, 2026):
    year_months = {k: v for k, v in monthly.items() if k.startswith(str(year))}
    if not year_months:
        continue
    t = sum(v['trades'] for v in year_months.values())
    w = sum(v['winners'] for v in year_months.values())
    pnl = sum(v['pnl'] for v in year_months.values())
    losing = sum(1 for v in year_months.values() if v['pnl'] < 0)
    wr = w/t*100 if t > 0 else 0
    print(f"{year:<8} {t:>8} {w:>8} {wr:>7.1f}% ${pnl:>16,.0f} {losing:>8}/{len(year_months)}")

# ============================================================
# PER-ASSET LIFETIME STATS
# ============================================================
print("\n" + "=" * 100)
print("PER-ASSET LIFETIME STATISTICS")
print("=" * 100)
print(f"{'Symbol':<12} {'Trades':>7} {'Win':>5} {'Loss':>5} {'WR%':>7} {'Net PnL':>18} {'Avg PnL':>12} {'PF':>6}")
print("-" * 80)

asset_stats = {}
for symbol in sorted(trade_groups['symbol'].unique()):
    sym_trades = trade_groups[trade_groups['symbol'] == symbol]
    total = len(sym_trades)
    wins = sym_trades['winner'].sum()
    losses = total - wins
    wr = wins / total * 100 if total > 0 else 0
    net_pnl = sym_trades['total_pnl'].sum()
    avg_pnl = net_pnl / total if total > 0 else 0

    # Profit factor
    gross_profit = sym_trades[sym_trades['total_pnl'] > 0]['total_pnl'].sum()
    gross_loss = abs(sym_trades[sym_trades['total_pnl'] <= 0]['total_pnl'].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    asset_stats[symbol] = {
        'trades': total, 'wins': wins, 'losses': losses,
        'wr': wr, 'net_pnl': net_pnl, 'avg_pnl': avg_pnl, 'pf': pf,
        'gross_profit': gross_profit, 'gross_loss': gross_loss
    }

    print(f"{symbol:<12} {total:>7} {wins:>5} {losses:>5} {wr:>6.1f}% ${net_pnl:>16,.0f} ${avg_pnl:>10,.0f} {pf:>5.2f}")

# ============================================================
# PER-ASSET PER-YEAR BREAKDOWN
# ============================================================
print("\n" + "=" * 100)
print("PER-ASSET PER-YEAR BREAKDOWN (WR% / PnL)")
print("=" * 100)

years = list(range(2015, 2026))
header = f"{'Symbol':<12}" + "".join(f"{'  ' + str(y):>12}" for y in years)
print(header)
print("-" * (12 + 12 * len(years)))

asset_year_data = {}
for symbol in sorted(trade_groups['symbol'].unique()):
    sym_trades = trade_groups[trade_groups['symbol'] == symbol]
    row = f"{symbol:<12}"
    yearly_data = {}
    for year in years:
        yt = sym_trades[sym_trades['year'] == year]
        if len(yt) == 0:
            row += f"{'---':>12}"
            yearly_data[year] = {'trades': 0, 'wr': 0, 'pnl': 0, 'profitable': None}
        else:
            wr = yt['winner'].mean() * 100
            pnl = yt['total_pnl'].sum()
            profitable = pnl > 0
            yearly_data[year] = {'trades': len(yt), 'wr': wr, 'pnl': pnl, 'profitable': profitable}
            marker = "+" if profitable else "-"
            row += f" {marker}{wr:.0f}%/{len(yt):>3}t"
    asset_year_data[symbol] = yearly_data
    print(row)

# ============================================================
# CONSISTENTLY LOSING ASSETS ANALYSIS
# ============================================================
print("\n" + "=" * 100)
print("ASSET PERFORMANCE ANALYSIS - CANDIDATES FOR REMOVAL")
print("=" * 100)

print("\n--- Assets ranked by Profit Factor (worst first) ---")
sorted_assets = sorted(asset_stats.items(), key=lambda x: x[1]['pf'])
for symbol, stats in sorted_assets:
    losing_years = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] == False)
    profitable_years = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] == True)
    no_data_years = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] is None)
    active_years = 11 - no_data_years

    print(f"\n{symbol}: PF={stats['pf']:.2f}, WR={stats['wr']:.1f}%, "
          f"Trades={stats['trades']}, Net=${stats['net_pnl']:,.0f}")
    print(f"  Profitable years: {profitable_years}/{active_years}, "
          f"Losing years: {losing_years}/{active_years}")

    # Show year-by-year
    year_details = []
    for y in years:
        yd = asset_year_data[symbol][y]
        if yd['trades'] > 0:
            marker = "+" if yd['profitable'] else "!!!"
            year_details.append(f"{y}:{marker}{yd['wr']:.0f}%({yd['trades']}t)")
    print(f"  Years: {', '.join(year_details)}")

# ============================================================
# RECOMMENDATION SUMMARY
# ============================================================
print("\n" + "=" * 100)
print("RECOMMENDATIONS")
print("=" * 100)

# Identify truly bad assets: PF < 1.0 OR losing more years than profitable
bad_assets = []
mediocre_assets = []
good_assets = []

for symbol, stats in asset_stats.items():
    losing_years = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] == False)
    profitable_years = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] == True)
    no_data_years = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] is None)
    active_years = 11 - no_data_years

    if stats['pf'] < 1.0:
        bad_assets.append((symbol, stats, losing_years, profitable_years, active_years))
    elif stats['pf'] < 1.2 or losing_years >= profitable_years * 0.6:
        mediocre_assets.append((symbol, stats, losing_years, profitable_years, active_years))
    else:
        good_assets.append((symbol, stats, losing_years, profitable_years, active_years))

if bad_assets:
    print("\n🔴 REMOVE - Net negative PnL (PF < 1.0):")
    for symbol, stats, ly, py, ay in sorted(bad_assets, key=lambda x: x[1]['pf']):
        print(f"  {symbol}: PF={stats['pf']:.2f}, WR={stats['wr']:.1f}%, "
              f"Net=${stats['net_pnl']:,.0f}, Losing {ly}/{ay} years")

if mediocre_assets:
    print("\n🟡 CONSIDER REMOVING - Marginal performance (PF 1.0-1.2 or many losing years):")
    for symbol, stats, ly, py, ay in sorted(mediocre_assets, key=lambda x: x[1]['pf']):
        print(f"  {symbol}: PF={stats['pf']:.2f}, WR={stats['wr']:.1f}%, "
              f"Net=${stats['net_pnl']:,.0f}, Losing {ly}/{ay} years")

if good_assets:
    print(f"\n🟢 KEEP - Good performers ({len(good_assets)} assets):")
    for symbol, stats, ly, py, ay in sorted(good_assets, key=lambda x: x[1]['pf'], reverse=True):
        print(f"  {symbol}: PF={stats['pf']:.2f}, WR={stats['wr']:.1f}%, "
              f"Net=${stats['net_pnl']:,.0f}, Profitable {py}/{ay} years")

# Summary table for easy copy
print("\n" + "=" * 100)
print("SUMMARY TABLE (sorted by Profit Factor)")
print("=" * 100)
print(f"{'Rank':<5} {'Symbol':<12} {'PF':>6} {'WR%':>7} {'Trades':>7} {'Prof Yrs':>10} {'Verdict':>10}")
print("-" * 60)
for i, (symbol, stats) in enumerate(sorted_assets, 1):
    ly = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] == False)
    py = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] == True)
    nd = sum(1 for y in years if asset_year_data[symbol][y]['profitable'] is None)
    ay = 11 - nd

    if stats['pf'] < 1.0:
        verdict = "REMOVE"
    elif stats['pf'] < 1.2:
        verdict = "MAYBE"
    else:
        verdict = "KEEP"

    print(f"{i:<5} {symbol:<12} {stats['pf']:>5.2f} {stats['wr']:>6.1f}% {stats['trades']:>7} {py:>4}/{ay:<4} {verdict:>10}")
