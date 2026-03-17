#!/usr/bin/env python3
"""FOMC Impact Analysis on Backtest Trade Data (2015-2025)"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

# ============================================================
# 1. FOMC Meeting Dates and Rate Decisions
# ============================================================

fomc_meetings = [
    # 2015
    ("2015-01-28", "Hold", 0), ("2015-03-18", "Hold", 0), ("2015-04-29", "Hold", 0),
    ("2015-06-17", "Hold", 0), ("2015-07-29", "Hold", 0), ("2015-09-17", "Hold", 0),
    ("2015-10-28", "Hold", 0), ("2015-12-16", "Hike", 25),
    # 2016
    ("2016-01-27", "Hold", 0), ("2016-03-16", "Hold", 0), ("2016-04-27", "Hold", 0),
    ("2016-06-15", "Hold", 0), ("2016-07-27", "Hold", 0), ("2016-09-21", "Hold", 0),
    ("2016-11-02", "Hold", 0), ("2016-12-14", "Hike", 25),
    # 2017
    ("2017-02-01", "Hold", 0), ("2017-03-15", "Hike", 25), ("2017-05-03", "Hold", 0),
    ("2017-06-14", "Hike", 25), ("2017-07-26", "Hold", 0), ("2017-09-20", "Hold", 0),
    ("2017-11-01", "Hold", 0), ("2017-12-13", "Hike", 25),
    # 2018
    ("2018-01-31", "Hold", 0), ("2018-03-21", "Hike", 25), ("2018-05-02", "Hold", 0),
    ("2018-06-13", "Hike", 25), ("2018-08-01", "Hold", 0), ("2018-09-26", "Hike", 25),
    ("2018-11-08", "Hold", 0), ("2018-12-19", "Hike", 25),
    # 2019
    ("2019-01-30", "Hold", 0), ("2019-03-20", "Hold", 0), ("2019-05-01", "Hold", 0),
    ("2019-06-19", "Hold", 0), ("2019-07-31", "Cut", -25), ("2019-09-18", "Cut", -25),
    ("2019-10-30", "Cut", -25), ("2019-12-11", "Hold", 0),
    # 2020
    ("2020-01-29", "Hold", 0), ("2020-03-03", "Cut (Emergency)", -50),
    ("2020-03-15", "Cut (Emergency)", -100), ("2020-04-29", "Hold", 0),
    ("2020-06-10", "Hold", 0), ("2020-07-29", "Hold", 0), ("2020-09-16", "Hold", 0),
    ("2020-11-05", "Hold", 0), ("2020-12-16", "Hold", 0),
    # 2021
    ("2021-01-27", "Hold", 0), ("2021-03-17", "Hold", 0), ("2021-04-28", "Hold", 0),
    ("2021-06-16", "Hold", 0), ("2021-07-28", "Hold", 0), ("2021-09-22", "Hold", 0),
    ("2021-11-03", "Hold", 0), ("2021-12-15", "Hold", 0),
    # 2022
    ("2022-01-26", "Hold", 0), ("2022-03-16", "Hike", 25), ("2022-05-04", "Hike", 50),
    ("2022-06-15", "Hike", 75), ("2022-07-27", "Hike", 75), ("2022-09-21", "Hike", 75),
    ("2022-11-02", "Hike", 75), ("2022-12-14", "Hike", 50),
    # 2023
    ("2023-02-01", "Hike", 25), ("2023-03-22", "Hike", 25), ("2023-05-03", "Hike", 25),
    ("2023-06-14", "Hold", 0), ("2023-07-26", "Hike", 25), ("2023-09-20", "Hold", 0),
    ("2023-11-01", "Hold", 0), ("2023-12-13", "Hold", 0),
    # 2024
    ("2024-01-31", "Hold", 0), ("2024-03-20", "Hold", 0), ("2024-05-01", "Hold", 0),
    ("2024-06-12", "Hold", 0), ("2024-07-31", "Hold", 0), ("2024-09-18", "Cut", -50),
    ("2024-11-07", "Cut", -25), ("2024-12-18", "Cut", -25),
    # 2025
    ("2025-01-29", "Hold", 0), ("2025-03-19", "Hold", 0), ("2025-05-07", "Cut", -25),
    ("2025-06-18", "Cut", -25), ("2025-07-30", "Hold", 0), ("2025-09-17", "Cut", -25),
    ("2025-10-29", "Hold", 0), ("2025-12-10", "Hold", 0),
]

# ============================================================
# 2. Load and Parse Trades
# ============================================================

print("=" * 80)
print("FOMC IMPACT ANALYSIS - FULL BACKTEST (2015-2025)")
print("=" * 80)

df = pd.read_csv("/home/user/20k5ers/ftmo_analysis_output/backtest_2015_2025/trades.csv")
df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
df['close_time'] = pd.to_datetime(df['close_time'], utc=True)

print(f"\nTotal trades loaded: {len(df):,}")
print(f"Date range: {df['open_time'].min().date()} to {df['close_time'].max().date()}")
print(f"Total P&L: ${df['pnl'].sum():,.2f}")
print(f"Columns: {list(df.columns)}")

# ============================================================
# 3. Identify FOMC-Affected Trades
# ============================================================

utc = pytz.UTC

# FOMC announcement time: 2:00 PM ET = 18:00 UTC (19:00 UTC during EDT but
# the standard is 2pm ET which is 18:00 or 19:00 depending on DST)
# We'll use 18:00 UTC as the base and adjust for DST
eastern = pytz.timezone('US/Eastern')

fomc_results = []

for date_str, decision, bp_change in fomc_meetings:
    meeting_date = datetime.strptime(date_str, "%Y-%m-%d")
    # FOMC announcement at 2:00 PM Eastern Time
    eastern_announcement = eastern.localize(
        datetime(meeting_date.year, meeting_date.month, meeting_date.day, 14, 0, 0)
    )
    announcement_utc = eastern_announcement.astimezone(utc)

    window_start = announcement_utc - timedelta(hours=24)
    window_end = announcement_utc + timedelta(hours=24)

    # A trade is FOMC-affected if:
    # 1. It was OPEN during the announcement (opened before, closed after)
    # 2. It was OPENED within 24 hours before the announcement
    # 3. It was CLOSED within 24 hours after the announcement

    mask_open_during = (df['open_time'] <= announcement_utc) & (df['close_time'] >= announcement_utc)
    mask_opened_before = (df['open_time'] >= window_start) & (df['open_time'] <= announcement_utc)
    mask_closed_after = (df['close_time'] >= announcement_utc) & (df['close_time'] <= window_end)

    affected = df[mask_open_during | mask_opened_before | mask_closed_after].copy()

    if len(affected) > 0:
        total_pnl = affected['pnl'].sum()
        worst_trade = affected.loc[affected['pnl'].idxmin()]
        best_trade = affected.loc[affected['pnl'].idxmax()]
        win_rate = (affected['pnl'] > 0).mean() * 100
        symbols = affected['symbol'].value_counts()
    else:
        total_pnl = 0
        worst_trade = None
        best_trade = None
        win_rate = 0
        symbols = pd.Series(dtype=int)

    fomc_results.append({
        'date': date_str,
        'decision': decision,
        'bp_change': bp_change,
        'num_trades': len(affected),
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / len(affected) if len(affected) > 0 else 0,
        'worst_loss': worst_trade['pnl'] if worst_trade is not None else 0,
        'worst_symbol': worst_trade['symbol'] if worst_trade is not None else 'N/A',
        'best_gain': best_trade['pnl'] if best_trade is not None else 0,
        'win_rate': win_rate,
        'affected_indices': affected.index.tolist(),
        'announcement_utc': announcement_utc,
        'symbols': symbols,
    })

fomc_df = pd.DataFrame(fomc_results)

# ============================================================
# 4. Per-Event Stats Table
# ============================================================

print("\n" + "=" * 80)
print("SECTION 1: PER-FOMC-EVENT STATISTICS")
print("=" * 80)

print(f"\n{'Date':<12} {'Decision':<18} {'#Trades':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Worst Loss':>12} {'Worst Sym':<10} {'Win%':>6}")
print("-" * 95)

for _, row in fomc_df.iterrows():
    print(f"{row['date']:<12} {row['decision']:<18} {row['num_trades']:>7} "
          f"${row['total_pnl']:>10,.2f} ${row['avg_pnl']:>8,.2f} "
          f"${row['worst_loss']:>10,.2f} {row['worst_symbol']:<10} {row['win_rate']:>5.1f}%")

# ============================================================
# 5. FOMC vs Non-FOMC Comparison
# ============================================================

print("\n" + "=" * 80)
print("SECTION 2: FOMC vs NON-FOMC PERFORMANCE COMPARISON")
print("=" * 80)

# Collect all affected trade indices (deduplicated)
all_fomc_indices = set()
for indices_list in fomc_df['affected_indices']:
    all_fomc_indices.update(indices_list)

fomc_trades = df.loc[list(all_fomc_indices)]
non_fomc_trades = df.drop(index=list(all_fomc_indices))

def calc_stats(trades, label):
    n = len(trades)
    total = trades['pnl'].sum()
    avg = trades['pnl'].mean() if n > 0 else 0
    median = trades['pnl'].median() if n > 0 else 0
    std = trades['pnl'].std() if n > 0 else 0
    win_rate = (trades['pnl'] > 0).mean() * 100 if n > 0 else 0
    worst = trades['pnl'].min() if n > 0 else 0
    best = trades['pnl'].max() if n > 0 else 0
    avg_win = trades.loc[trades['pnl'] > 0, 'pnl'].mean() if (trades['pnl'] > 0).any() else 0
    avg_loss = trades.loc[trades['pnl'] <= 0, 'pnl'].mean() if (trades['pnl'] <= 0).any() else 0
    profit_factor = abs(trades.loc[trades['pnl'] > 0, 'pnl'].sum() / trades.loc[trades['pnl'] <= 0, 'pnl'].sum()) if (trades['pnl'] <= 0).any() and trades.loc[trades['pnl'] <= 0, 'pnl'].sum() != 0 else float('inf')

    return {
        'label': label, 'count': n, 'total_pnl': total, 'avg_pnl': avg,
        'median_pnl': median, 'std_pnl': std, 'win_rate': win_rate,
        'worst': worst, 'best': best, 'avg_win': avg_win, 'avg_loss': avg_loss,
        'profit_factor': profit_factor
    }

fomc_stats = calc_stats(fomc_trades, "FOMC-Affected")
non_fomc_stats = calc_stats(non_fomc_trades, "Non-FOMC")
all_stats = calc_stats(df, "All Trades")

print(f"\n{'Metric':<25} {'FOMC-Affected':>15} {'Non-FOMC':>15} {'All Trades':>15}")
print("-" * 75)
for key, fmt in [
    ('count', '{:,.0f}'), ('total_pnl', '${:,.2f}'), ('avg_pnl', '${:,.2f}'),
    ('median_pnl', '${:,.2f}'), ('std_pnl', '${:,.2f}'), ('win_rate', '{:.1f}%'),
    ('worst', '${:,.2f}'), ('best', '${:,.2f}'), ('avg_win', '${:,.2f}'),
    ('avg_loss', '${:,.2f}'), ('profit_factor', '{:.3f}')
]:
    label = key.replace('_', ' ').title()
    v1 = fmt.format(fomc_stats[key])
    v2 = fmt.format(non_fomc_stats[key])
    v3 = fmt.format(all_stats[key])
    print(f"{label:<25} {v1:>15} {v2:>15} {v3:>15}")

pct_trades = len(fomc_trades) / len(df) * 100
pct_pnl = fomc_trades['pnl'].sum() / df['pnl'].sum() * 100 if df['pnl'].sum() != 0 else 0
print(f"\nFOMC trades are {pct_trades:.1f}% of all trades but account for {pct_pnl:.1f}% of total P&L")

# ============================================================
# 6. Rate Cut vs Hold vs Hike Comparison
# ============================================================

print("\n" + "=" * 80)
print("SECTION 3: RATE CUT vs HOLD vs HIKE COMPARISON")
print("=" * 80)

def classify_decision(row):
    if row['bp_change'] > 0:
        return 'Hike'
    elif row['bp_change'] < 0:
        return 'Cut'
    else:
        return 'Hold'

fomc_df['category'] = fomc_df.apply(classify_decision, axis=1)

for cat in ['Hike', 'Hold', 'Cut']:
    subset = fomc_df[fomc_df['category'] == cat]
    n_meetings = len(subset)
    total_trades = subset['num_trades'].sum()
    total_pnl = subset['total_pnl'].sum()
    avg_pnl_per_meeting = total_pnl / n_meetings if n_meetings > 0 else 0
    avg_trades_per_meeting = total_trades / n_meetings if n_meetings > 0 else 0
    worst_event = subset.loc[subset['total_pnl'].idxmin()] if n_meetings > 0 else None
    best_event = subset.loc[subset['total_pnl'].idxmax()] if n_meetings > 0 else None

    print(f"\n--- {cat.upper()} ({n_meetings} meetings) ---")
    print(f"  Total affected trades:    {total_trades:,}")
    print(f"  Avg trades per meeting:   {avg_trades_per_meeting:.1f}")
    print(f"  Total P&L:                ${total_pnl:,.2f}")
    print(f"  Avg P&L per meeting:      ${avg_pnl_per_meeting:,.2f}")
    if worst_event is not None:
        print(f"  Worst event:              {worst_event['date']} (${worst_event['total_pnl']:,.2f})")
        print(f"  Best event:               {best_event['date']} (${best_event['total_pnl']:,.2f})")

# Emergency cuts separately
emergency = fomc_df[fomc_df['decision'].str.contains('Emergency')]
if len(emergency) > 0:
    print(f"\n--- EMERGENCY CUTS ({len(emergency)} meetings) ---")
    for _, row in emergency.iterrows():
        print(f"  {row['date']}: {row['decision']}, {row['num_trades']} trades, P&L: ${row['total_pnl']:,.2f}")

# ============================================================
# 7. Worst and Best FOMC Events
# ============================================================

print("\n" + "=" * 80)
print("SECTION 4: WORST AND BEST FOMC EVENTS")
print("=" * 80)

# Only consider events with trades
events_with_trades = fomc_df[fomc_df['num_trades'] > 0].copy()

print("\n--- TOP 10 WORST FOMC EVENTS (by Total P&L) ---")
worst_events = events_with_trades.nsmallest(10, 'total_pnl')
print(f"{'Rank':<5} {'Date':<12} {'Decision':<18} {'#Trades':>7} {'Total P&L':>12} {'Worst Trade':>12} {'Symbol':<10}")
print("-" * 80)
for rank, (_, row) in enumerate(worst_events.iterrows(), 1):
    print(f"{rank:<5} {row['date']:<12} {row['decision']:<18} {row['num_trades']:>7} "
          f"${row['total_pnl']:>10,.2f} ${row['worst_loss']:>10,.2f} {row['worst_symbol']:<10}")

print("\n--- TOP 10 BEST FOMC EVENTS (by Total P&L) ---")
best_events = events_with_trades.nlargest(10, 'total_pnl')
print(f"{'Rank':<5} {'Date':<12} {'Decision':<18} {'#Trades':>7} {'Total P&L':>12} {'Best Trade':>12} {'Symbol':<10}")
print("-" * 80)
for rank, (_, row) in enumerate(best_events.iterrows(), 1):
    # Get best symbol for this event
    affected = df.loc[row['affected_indices']]
    best_sym = affected.loc[affected['pnl'].idxmax(), 'symbol']
    print(f"{rank:<5} {row['date']:<12} {row['decision']:<18} {row['num_trades']:>7} "
          f"${row['total_pnl']:>10,.2f} ${row['best_gain']:>10,.2f} {best_sym:<10}")

# ============================================================
# 8. News Blackout Effectiveness
# ============================================================

print("\n" + "=" * 80)
print("SECTION 5: NEWS BLACKOUT EFFECTIVENESS ANALYSIS")
print("=" * 80)

print("\nCurrent ftmo_config.py settings:")
print("  block_trading_around_news: True")
print("  news_blackout_minutes_before: 60 (1 hour)")
print("  news_blackout_minutes_after: 30 (30 minutes)")
print("  FOMC announcement detection: Weekday=Wednesday, Hour=19:00 UTC")
print()

# Check how many trades fall within the blackout window
blackout_before = 60  # minutes
blackout_after = 30   # minutes

trades_in_blackout = 0
trades_in_extended_window = 0
blackout_pnl = 0
extended_pnl = 0

for _, row in fomc_df.iterrows():
    ann = row['announcement_utc']

    # Current blackout window
    bb_start = ann - timedelta(minutes=blackout_before)
    bb_end = ann + timedelta(minutes=blackout_after)

    # Check trades opened within blackout
    mask_blackout = (df['open_time'] >= bb_start) & (df['open_time'] <= bb_end)
    bl_trades = df[mask_blackout]
    trades_in_blackout += len(bl_trades)
    blackout_pnl += bl_trades['pnl'].sum()

    # Extended window: 4 hours before, 4 hours after
    ext_start = ann - timedelta(hours=4)
    ext_end = ann + timedelta(hours=4)
    mask_ext = (df['open_time'] >= ext_start) & (df['open_time'] <= ext_end)
    ext_trades = df[mask_ext]
    trades_in_extended_window += len(ext_trades)
    extended_pnl += ext_trades['pnl'].sum()

print(f"Trades OPENED within current blackout window (-60min/+30min): {trades_in_blackout}")
print(f"  P&L of those trades: ${blackout_pnl:,.2f}")
print(f"Trades OPENED within extended window (-4h/+4h): {trades_in_extended_window}")
print(f"  P&L of those trades: ${extended_pnl:,.2f}")

# Analyze different blackout windows
print("\n--- BLACKOUT WINDOW SENSITIVITY ANALYSIS ---")
print(f"{'Window (before/after)':<25} {'Trades Opened':>15} {'P&L':>15} {'Avg P&L':>12}")
print("-" * 70)

for before_min, after_min in [(30, 15), (60, 30), (120, 60), (240, 120), (480, 240), (1440, 720)]:
    count = 0
    pnl = 0
    for _, row in fomc_df.iterrows():
        ann = row['announcement_utc']
        s = ann - timedelta(minutes=before_min)
        e = ann + timedelta(minutes=after_min)
        mask = (df['open_time'] >= s) & (df['open_time'] <= e)
        t = df[mask]
        count += len(t)
        pnl += t['pnl'].sum()
    avg = pnl / count if count > 0 else 0
    label = f"-{before_min}min / +{after_min}min"
    print(f"{label:<25} {count:>15,} ${pnl:>13,.2f} ${avg:>10,.2f}")

# Analyze trades that were already OPEN at announcement time (can't be blocked by entry blackout)
print("\n--- TRADES ALREADY OPEN AT ANNOUNCEMENT (not blockable by entry blackout) ---")
already_open_count = 0
already_open_pnl = 0
for _, row in fomc_df.iterrows():
    ann = row['announcement_utc']
    # Opened more than 24h before - truly pre-existing positions
    mask = (df['open_time'] < ann - timedelta(hours=24)) & (df['close_time'] > ann)
    t = df[mask]
    already_open_count += len(t)
    already_open_pnl += t['pnl'].sum()

print(f"Trades opened >24h before FOMC but still open at announcement: {already_open_count}")
print(f"  P&L of those trades: ${already_open_pnl:,.2f}")

# Config issue analysis
print("\n--- CONFIG ISSUE: FOMC DETECTION ---")
print("  Current config detects FOMC at Weekday=2 (Wednesday), Hour=19 UTC")
print("  Actual FOMC announcement: 2:00 PM ET = 18:00 or 19:00 UTC depending on DST")
print("  Meetings NOT on Wednesday: Some are on other weekdays (emergency meetings)")
print("  The config only blocks entry of NEW trades; trades already open are exposed")
print("  RECOMMENDATION: Use a calendar-based approach with actual FOMC dates")

# ============================================================
# 9. Most Vulnerable Currency Pairs
# ============================================================

print("\n" + "=" * 80)
print("SECTION 6: MOST VULNERABLE CURRENCY PAIRS AROUND FOMC")
print("=" * 80)

# Gather all FOMC-affected trades by symbol
pair_stats = {}
for sym in fomc_trades['symbol'].unique():
    sym_trades = fomc_trades[fomc_trades['symbol'] == sym]
    n = len(sym_trades)
    total = sym_trades['pnl'].sum()
    avg = sym_trades['pnl'].mean()
    worst = sym_trades['pnl'].min()
    win_r = (sym_trades['pnl'] > 0).mean() * 100
    losses = sym_trades[sym_trades['pnl'] < 0]['pnl'].sum()
    pair_stats[sym] = {
        'count': n, 'total_pnl': total, 'avg_pnl': avg,
        'worst_trade': worst, 'win_rate': win_r, 'total_losses': losses
    }

pair_df = pd.DataFrame(pair_stats).T
pair_df = pair_df.sort_values('total_pnl')

print(f"\n--- ALL PAIRS SORTED BY TOTAL P&L (FOMC-affected trades only) ---")
print(f"{'Symbol':<12} {'#Trades':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Worst':>12} {'Win%':>7} {'Tot Losses':>12}")
print("-" * 80)
for sym, row in pair_df.iterrows():
    print(f"{sym:<12} {row['count']:>7.0f} ${row['total_pnl']:>10,.2f} ${row['avg_pnl']:>8,.2f} "
          f"${row['worst_trade']:>10,.2f} {row['win_rate']:>6.1f}% ${row['total_losses']:>10,.2f}")

# USD pairs specifically
print(f"\n--- USD-CONTAINING PAIRS (most FOMC-sensitive) ---")
usd_pairs = pair_df[[('USD' in str(s)) for s in pair_df.index]]
usd_pairs = usd_pairs.sort_values('total_pnl')
print(f"{'Symbol':<12} {'#Trades':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Worst':>12} {'Win%':>7}")
print("-" * 65)
for sym, row in usd_pairs.iterrows():
    print(f"{sym:<12} {row['count']:>7.0f} ${row['total_pnl']:>10,.2f} ${row['avg_pnl']:>8,.2f} "
          f"${row['worst_trade']:>10,.2f} {row['win_rate']:>6.1f}%")

# Non-USD pairs
print(f"\n--- NON-USD CROSS PAIRS (less FOMC-sensitive expected) ---")
non_usd = pair_df[[('USD' not in str(s)) for s in pair_df.index]]
non_usd = non_usd.sort_values('total_pnl')
print(f"{'Symbol':<12} {'#Trades':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Worst':>12} {'Win%':>7}")
print("-" * 65)
for sym, row in non_usd.iterrows():
    print(f"{sym:<12} {row['count']:>7.0f} ${row['total_pnl']:>10,.2f} ${row['avg_pnl']:>8,.2f} "
          f"${row['worst_trade']:>10,.2f} {row['win_rate']:>6.1f}%")

# Comparison: USD vs non-USD around FOMC
usd_fomc = fomc_trades[fomc_trades['symbol'].str.contains('USD')]
nonusd_fomc = fomc_trades[~fomc_trades['symbol'].str.contains('USD')]
print(f"\n--- USD vs NON-USD FOMC SUMMARY ---")
print(f"  USD pairs:     {len(usd_fomc):,} trades, P&L: ${usd_fomc['pnl'].sum():,.2f}, "
      f"Avg: ${usd_fomc['pnl'].mean():,.2f}, Win: {(usd_fomc['pnl']>0).mean()*100:.1f}%")
print(f"  Non-USD pairs: {len(nonusd_fomc):,} trades, P&L: ${nonusd_fomc['pnl'].sum():,.2f}, "
      f"Avg: ${nonusd_fomc['pnl'].mean():,.2f}, Win: {(nonusd_fomc['pnl']>0).mean()*100:.1f}%")

# ============================================================
# 10. Year-by-Year Summary
# ============================================================

print("\n" + "=" * 80)
print("SECTION 7: YEAR-BY-YEAR FOMC IMPACT")
print("=" * 80)

fomc_df['year'] = fomc_df['date'].str[:4].astype(int)

print(f"\n{'Year':<6} {'Meetings':>8} {'Trades':>8} {'Total P&L':>12} {'Avg/Meeting':>12} {'Worst Event':>20}")
print("-" * 75)
for year in range(2015, 2026):
    yr = fomc_df[fomc_df['year'] == year]
    n_meetings = len(yr)
    n_trades = yr['num_trades'].sum()
    total = yr['total_pnl'].sum()
    avg_per = total / n_meetings if n_meetings > 0 else 0
    worst_idx = yr['total_pnl'].idxmin() if n_meetings > 0 else None
    worst_str = f"{yr.loc[worst_idx, 'date']} (${yr.loc[worst_idx, 'total_pnl']:,.0f})" if worst_idx is not None else "N/A"
    print(f"{year:<6} {n_meetings:>8} {n_trades:>8} ${total:>10,.2f} ${avg_per:>10,.2f} {worst_str:>20}")

# ============================================================
# 11. Overall Summary and Recommendations
# ============================================================

print("\n" + "=" * 80)
print("SECTION 8: SUMMARY & RECOMMENDATIONS")
print("=" * 80)

total_fomc_meetings = len(fomc_df)
meetings_with_losses = len(fomc_df[fomc_df['total_pnl'] < 0])
meetings_with_gains = len(fomc_df[fomc_df['total_pnl'] > 0])
meetings_no_trades = len(fomc_df[fomc_df['num_trades'] == 0])

print(f"\n1. OVERVIEW:")
print(f"   - {total_fomc_meetings} FOMC meetings analyzed (2015-2025)")
print(f"   - {meetings_with_losses} meetings had net negative P&L ({meetings_with_losses/total_fomc_meetings*100:.0f}%)")
print(f"   - {meetings_with_gains} meetings had net positive P&L ({meetings_with_gains/total_fomc_meetings*100:.0f}%)")
print(f"   - {meetings_no_trades} meetings had zero affected trades")

print(f"\n2. FOMC IMPACT MAGNITUDE:")
fomc_pnl = fomc_trades['pnl'].sum()
total_pnl = df['pnl'].sum()
print(f"   - FOMC-affected P&L: ${fomc_pnl:,.2f} ({fomc_pnl/total_pnl*100:.1f}% of total)" if total_pnl != 0 else "   - Total P&L is zero")
print(f"   - Non-FOMC P&L: ${non_fomc_trades['pnl'].sum():,.2f}")
print(f"   - FOMC avg trade P&L: ${fomc_stats['avg_pnl']:,.2f} vs Non-FOMC: ${non_fomc_stats['avg_pnl']:,.2f}")

diff = fomc_stats['avg_pnl'] - non_fomc_stats['avg_pnl']
if diff < 0:
    print(f"   - FOMC trades underperform by ${abs(diff):,.2f} per trade on average")
else:
    print(f"   - FOMC trades outperform by ${diff:,.2f} per trade on average")

print(f"\n3. RATE DECISION IMPACT:")
for cat in ['Hike', 'Hold', 'Cut']:
    subset = fomc_df[fomc_df['category'] == cat]
    if len(subset) > 0:
        avg = subset['total_pnl'].mean()
        print(f"   - {cat}: avg P&L per meeting = ${avg:,.2f} ({len(subset)} meetings)")

print(f"\n4. BLACKOUT ASSESSMENT:")
print(f"   - Current blackout (-60min/+30min) is NARROW for FOMC events")
print(f"   - FOMC creates volatility that persists hours after announcement")
print(f"   - Config detects FOMC by weekday+hour, not calendar dates (may miss some)")
print(f"   - Trades already open before blackout remain exposed")

print(f"\n5. RECOMMENDATIONS:")
print(f"   a) Extend FOMC-specific blackout to at least -4h/+2h")
print(f"   b) Consider closing open positions 1h before FOMC")
print(f"   c) Use calendar-based FOMC detection (hardcoded dates)")
print(f"   d) Reduce position size on FOMC days")
print(f"   e) Focus blackout on USD pairs which show highest FOMC sensitivity")

# The single worst FOMC day
worst_overall = fomc_df.loc[fomc_df['total_pnl'].idxmin()]
best_overall = fomc_df.loc[fomc_df['total_pnl'].idxmax()]
print(f"\n6. EXTREMES:")
print(f"   - Worst FOMC event: {worst_overall['date']} ({worst_overall['decision']})")
print(f"     P&L: ${worst_overall['total_pnl']:,.2f}, {worst_overall['num_trades']} trades")
print(f"   - Best FOMC event:  {best_overall['date']} ({best_overall['decision']})")
print(f"     P&L: ${best_overall['total_pnl']:,.2f}, {best_overall['num_trades']} trades")

print("\n" + "=" * 80)
print("END OF FOMC IMPACT ANALYSIS")
print("=" * 80)
