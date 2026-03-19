#!/usr/bin/env python3
"""
Re-entry impact analysis for 2015-2017 period.
Includes daily safety tier simulation (DDD hits).
"""

import pandas as pd
import numpy as np
from collections import defaultdict

pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 140)

# =============================================================================
# CONFIG - Daily Safety Tiers
# =============================================================================
ACCOUNT_SIZE = 20000.0
MAX_DAILY_LOSS_PCT = 5.0     # Hard limit (5ers rule)
DAILY_WARNING_PCT = 2.0       # Tier 1: warning
DAILY_REDUCE_PCT = 3.0        # Tier 2: reduce risk
DAILY_HALT_PCT = 3.2          # Tier 3: close all
RISK_PER_TRADE_PCT = 0.6      # Normal risk

# =============================================================================
# LOAD & PREPARE DATA
# =============================================================================
df = pd.read_csv('/home/user/20k5ers/ftmo_analysis_output/backtest_2015_2025/trades.csv')
df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
df['close_time'] = pd.to_datetime(df['close_time'], utc=True)
df['base_ticket'] = df['ticket'].str.extract(r'^(\d+)')[0]
df['is_partial'] = df['ticket'].str.contains('_partial_')

# Reconstruct trades
trade_list = []
for base_id, group in df.groupby('base_ticket'):
    group = group.sort_values('close_time')
    partials = group[group['is_partial']]
    final = group[~group['is_partial']]

    symbol = group['symbol'].iloc[0]
    direction = group['type'].iloc[0]
    entry_price = group['open_price'].iloc[0]
    open_time = group['open_time'].iloc[0]
    sl = group['sl'].iloc[0]

    total_pnl = group['pnl'].sum()
    n_partials = len(partials)
    tp1_hit = n_partials >= 1

    last_row = final.iloc[-1] if len(final) > 0 else partials.iloc[-1]
    final_close_time = last_row['close_time']
    final_close_price = last_row['close_price']

    if direction == 'buy':
        risk_distance = abs(entry_price - sl)
        move_distance = final_close_price - entry_price
    else:
        risk_distance = abs(sl - entry_price)
        move_distance = entry_price - final_close_price

    final_r = move_distance / risk_distance if risk_distance > 0 else 0

    # Collect individual close events for daily P&L tracking
    close_events = []
    for _, row in group.iterrows():
        close_events.append({
            'close_time': row['close_time'],
            'pnl': row['pnl'],
        })

    trade_list.append({
        'base_ticket': base_id,
        'symbol': symbol,
        'direction': direction,
        'entry_price': entry_price,
        'open_time': open_time,
        'close_time': final_close_time,
        'total_pnl': total_pnl,
        'n_partials': n_partials,
        'tp1_hit': tp1_hit,
        'final_r': final_r,
        'risk_distance': risk_distance,
        'close_events': close_events,
    })

trades = pd.DataFrame(trade_list)
trades['open_time'] = pd.to_datetime(trades['open_time'], utc=True)
trades['close_time'] = pd.to_datetime(trades['close_time'], utc=True)

# FILTER: 2015-2017 only
trades_period = trades[
    (trades['open_time'] >= '2015-01-01') &
    (trades['open_time'] < '2018-01-01')
].copy().sort_values('open_time').reset_index(drop=True)

print("=" * 110)
print("RE-ENTRY & DAILY SAFETY ANALYSIS: 2015-2017")
print("=" * 110)
print(f"\nTrades in 2015-2017: {len(trades_period)}")
print(f"Total P&L: ${trades_period['total_pnl'].sum():,.2f}")
print(f"TP1 hit rate: {trades_period['tp1_hit'].mean()*100:.1f}%")
print(f"Avg P&L: ${trades_period['total_pnl'].mean():,.2f}")

# =============================================================================
# SECTION 1: Basic re-entry stats for 2015-2017
# =============================================================================
print("\n" + "=" * 110)
print("SECTION 1: RE-ENTRY STATISTIEKEN 2015-2017")
print("=" * 110)

tp1_trades = trades_period[trades_period['tp1_hit']].copy()
print(f"\nTrades met TP1 hit: {len(tp1_trades)} ({len(tp1_trades)/len(trades_period)*100:.1f}%)")

def categorize_r(r):
    if r < -0.1: return 'Negative (<-0.1R)'
    elif r < 0.1: return 'Breakeven'
    elif r < 0.5: return 'Low R (0.1-0.5)'
    elif r < 1.0: return 'Medium R (0.5-1.0)'
    else: return 'High R (>1.0)'

tp1_trades['r_cat'] = tp1_trades['final_r'].apply(categorize_r)
print("\nFinal R distributie (TP1-hit trades):")
for cat in ['Negative (<-0.1R)', 'Breakeven', 'Low R (0.1-0.5)', 'Medium R (0.5-1.0)', 'High R (>1.0)']:
    count = (tp1_trades['r_cat'] == cat).sum()
    if count > 0:
        avg = tp1_trades[tp1_trades['r_cat'] == cat]['total_pnl'].mean()
        print(f"  {cat:25s}: {count:5d} ({count/len(tp1_trades)*100:5.1f}%)  Avg P&L: ${avg:>8,.2f}")

disappointing = tp1_trades[tp1_trades['final_r'] < 0.5].copy()
print(f"\n'Disappointing' (TP1 hit, R<0.5): {len(disappointing)} ({len(disappointing)/len(tp1_trades)*100:.1f}%)")


# =============================================================================
# COOLDOWN SIMULATION WITH DAILY SAFETY TRACKING
# =============================================================================

def simulate_with_daily_safety(trades_df, cooldown_days=0, price_threshold_pct=1.0,
                                only_after_low_r=False, low_r_threshold=0.5):
    """
    Simulate trading with optional cooldown, tracking daily P&L and safety tier hits.
    Returns stats dict.
    """
    trades_sorted = trades_df.sort_values('open_time').reset_index(drop=True)
    recent_closes = {}

    kept_trades = []
    blocked_trades = []

    for _, trade in trades_sorted.iterrows():
        should_block = False

        if cooldown_days > 0:
            key = (trade['symbol'], trade['direction'])
            if key in recent_closes:
                for prev in recent_closes[key]:
                    time_diff = (trade['open_time'] - prev['close_time']).total_seconds() / 86400
                    if time_diff < 0 or time_diff > cooldown_days:
                        continue
                    price_diff = abs(trade['entry_price'] - prev['entry_price']) / prev['entry_price'] * 100
                    if price_diff > price_threshold_pct:
                        continue
                    if only_after_low_r and prev['final_r'] >= low_r_threshold:
                        continue
                    should_block = True
                    break

        if should_block:
            blocked_trades.append(trade)
        else:
            kept_trades.append(trade)
            if cooldown_days > 0:
                key = (trade['symbol'], trade['direction'])
                if key not in recent_closes:
                    recent_closes[key] = []
                recent_closes[key].append({
                    'close_time': trade['close_time'],
                    'entry_price': trade['entry_price'],
                    'final_r': trade['final_r'],
                })
                cutoff = trade['open_time'] - pd.Timedelta(days=cooldown_days + 1)
                recent_closes[key] = [x for x in recent_closes[key] if x['close_time'] > cutoff]

    kept_df = pd.DataFrame(kept_trades) if kept_trades else pd.DataFrame()
    blocked_df = pd.DataFrame(blocked_trades) if blocked_trades else pd.DataFrame()

    # Now compute daily P&L from kept trades' close events
    daily_pnl = defaultdict(float)
    if len(kept_df) > 0:
        for _, trade in kept_df.iterrows():
            for evt in trade['close_events']:
                day = evt['close_time'].strftime('%Y-%m-%d')
                daily_pnl[day] += evt['pnl']

    # Compute daily safety stats
    daily_data = []
    for day, pnl in sorted(daily_pnl.items()):
        daily_loss_pct = max(0, -pnl) / ACCOUNT_SIZE * 100  # positive = loss
        daily_data.append({
            'date': day,
            'pnl': pnl,
            'daily_loss_pct': daily_loss_pct,
            'hit_warning': daily_loss_pct >= DAILY_WARNING_PCT,
            'hit_reduce': daily_loss_pct >= DAILY_REDUCE_PCT,
            'hit_halt': daily_loss_pct >= DAILY_HALT_PCT,
            'hit_max': daily_loss_pct >= MAX_DAILY_LOSS_PCT,
        })

    daily_df = pd.DataFrame(daily_data) if daily_data else pd.DataFrame()

    stats = {
        'n_kept': len(kept_df),
        'n_blocked': len(blocked_df),
        'kept_pnl': kept_df['total_pnl'].sum() if len(kept_df) > 0 else 0,
        'blocked_pnl': blocked_df['total_pnl'].sum() if len(blocked_df) > 0 else 0,
        'n_days': len(daily_df),
        'n_loss_days': (daily_df['pnl'] < 0).sum() if len(daily_df) > 0 else 0,
        'n_warning': daily_df['hit_warning'].sum() if len(daily_df) > 0 else 0,
        'n_reduce': daily_df['hit_reduce'].sum() if len(daily_df) > 0 else 0,
        'n_halt': daily_df['hit_halt'].sum() if len(daily_df) > 0 else 0,
        'n_max': daily_df['hit_max'].sum() if len(daily_df) > 0 else 0,
        'worst_day_pnl': daily_df['pnl'].min() if len(daily_df) > 0 else 0,
        'worst_day_pct': daily_df['daily_loss_pct'].max() if len(daily_df) > 0 else 0,
        'avg_loss_day': daily_df[daily_df['pnl'] < 0]['pnl'].mean() if len(daily_df) > 0 and (daily_df['pnl'] < 0).any() else 0,
        'daily_df': daily_df,
        'kept_df': kept_df,
        'blocked_df': blocked_df,
    }
    return stats


# =============================================================================
# RUN ALL SCENARIOS
# =============================================================================
print("\n" + "=" * 110)
print("SECTION 2: COOLDOWN IMPACT + DAILY SAFETY TIERS (2015-2017)")
print("=" * 110)

baseline = simulate_with_daily_safety(trades_period, cooldown_days=0)

print(f"\n--- BASELINE (geen cooldown) ---")
print(f"  Trades: {baseline['n_kept']}")
print(f"  P&L: ${baseline['kept_pnl']:,.2f}")
print(f"  Trading days: {baseline['n_days']}")
print(f"  Loss days: {baseline['n_loss_days']}")
print(f"  Worst day: ${baseline['worst_day_pnl']:,.2f} ({baseline['worst_day_pct']:.2f}% loss)")
print(f"  Avg loss day: ${baseline['avg_loss_day']:,.2f}")
print(f"  Tier 1 WARNING hits (≥{DAILY_WARNING_PCT}%): {baseline['n_warning']}")
print(f"  Tier 2 REDUCE hits (≥{DAILY_REDUCE_PCT}%):  {baseline['n_reduce']}")
print(f"  Tier 3 HALT hits (≥{DAILY_HALT_PCT}%):    {baseline['n_halt']}")
print(f"  MAX DAILY LOSS hits (≥{MAX_DAILY_LOSS_PCT}%): {baseline['n_max']}")

scenarios = [
    ("Geen cooldown", 0, 0, False, 0),
    ("1d / 0.5% / alle", 1, 0.5, False, 0),
    ("1d / 1.0% / alle", 1, 1.0, False, 0),
    ("2d / 0.5% / alle", 2, 0.5, False, 0),
    ("2d / 1.0% / alle", 2, 1.0, False, 0),
    ("3d / 0.5% / alle", 3, 0.5, False, 0),
    ("3d / 1.0% / alle", 3, 1.0, False, 0),
    ("5d / 1.0% / alle", 5, 1.0, False, 0),
    ("1d / 1% / R<0.5", 1, 1.0, True, 0.5),
    ("2d / 1% / R<0.5", 2, 1.0, True, 0.5),
    ("3d / 1% / R<0.5", 3, 1.0, True, 0.5),
    ("5d / 1% / R<0.5", 5, 1.0, True, 0.5),
    ("1d / 1% / R<0.2", 1, 1.0, True, 0.2),
    ("2d / 1% / R<0.2", 2, 1.0, True, 0.2),
    ("3d / 1% / R<0.2", 3, 1.0, True, 0.2),
    ("5d / 1% / R<0.2", 5, 1.0, True, 0.2),
    ("1d / 1% / R<0", 1, 1.0, True, 0.0),
    ("2d / 1% / R<0", 2, 1.0, True, 0.0),
    ("3d / 1% / R<0", 3, 1.0, True, 0.0),
    ("5d / 1% / R<0", 5, 1.0, True, 0.0),
]

print(f"\n{'Scenario':<22} {'Trades':>7} {'Blckd':>6} {'P&L':>12} {'ΔP&L%':>7} "
      f"{'Warn':>5} {'Reduce':>7} {'HALT':>5} {'MAX':>4} "
      f"{'Worst Day':>11} {'Worst%':>7} {'LossDays':>9}")
print("-" * 130)

results = []
for label, days, price, low_r, r_thresh in scenarios:
    stats = simulate_with_daily_safety(trades_period, days, price, low_r, r_thresh)
    delta_pct = (stats['kept_pnl'] - baseline['kept_pnl']) / baseline['kept_pnl'] * 100 if baseline['kept_pnl'] != 0 else 0

    results.append((label, stats, delta_pct))

    marker = " <+" if delta_pct > 0 else ""
    print(f"{label:<22} {stats['n_kept']:>7} {stats['n_blocked']:>6} ${stats['kept_pnl']:>10,.0f} {delta_pct:>+6.1f}% "
          f"{stats['n_warning']:>5} {stats['n_reduce']:>7} {stats['n_halt']:>5} {stats['n_max']:>4} "
          f"${stats['worst_day_pnl']:>9,.0f} {stats['worst_day_pct']:>6.2f}% {stats['n_loss_days']:>9}{marker}")

# =============================================================================
# SECTION 3: DETAILED DAILY SAFETY COMPARISON
# =============================================================================
print("\n" + "=" * 110)
print("SECTION 3: DAILY SAFETY VERGELIJKING - BASELINE vs BESTE SCENARIO'S")
print("=" * 110)

# Compare baseline with a few scenarios
for label, stats, delta_pct in results:
    if label in ["Geen cooldown", "2d / 1.0% / alle", "3d / 1% / R<0.5", "3d / 1% / R<0.2", "3d / 1% / R<0"]:
        print(f"\n--- {label} ---")
        print(f"  P&L: ${stats['kept_pnl']:>12,.2f} ({delta_pct:+.1f}%)")
        print(f"  Trades: {stats['n_kept']} (blocked: {stats['n_blocked']})")
        print(f"  Trading days: {stats['n_days']}")
        print(f"  Loss days: {stats['n_loss_days']} ({stats['n_loss_days']/stats['n_days']*100:.1f}%)" if stats['n_days'] > 0 else "")
        print(f"  Tier 1 WARNING (≥2.0%): {stats['n_warning']} days")
        print(f"  Tier 2 REDUCE  (≥3.0%): {stats['n_reduce']} days")
        print(f"  Tier 3 HALT    (≥3.2%): {stats['n_halt']} days")
        print(f"  MAX LOSS       (≥5.0%): {stats['n_max']} days")
        print(f"  Worst day: ${stats['worst_day_pnl']:,.2f} ({stats['worst_day_pct']:.2f}%)")
        print(f"  Avg loss day: ${stats['avg_loss_day']:,.2f}")

# =============================================================================
# SECTION 4: Show the actual WARNING/HALT days
# =============================================================================
print("\n" + "=" * 110)
print("SECTION 4: DAGEN MET SAFETY TIER HITS - BASELINE")
print("=" * 110)

base_daily = baseline['daily_df']
warning_days = base_daily[base_daily['hit_warning']].sort_values('pnl')

if len(warning_days) > 0:
    print(f"\nDagen met ≥2% daily loss ({len(warning_days)} dagen):")
    print(f"{'Date':<12} {'P&L':>12} {'Loss%':>8} {'Warning':>8} {'Reduce':>8} {'HALT':>6} {'MAX':>5}")
    print("-" * 65)
    for _, day in warning_days.iterrows():
        print(f"{day['date']:<12} ${day['pnl']:>10,.2f} {day['daily_loss_pct']:>7.2f}% "
              f"{'YES':>8} {'YES' if day['hit_reduce'] else '-':>8} "
              f"{'YES' if day['hit_halt'] else '-':>6} {'YES' if day['hit_max'] else '-':>5}")

# =============================================================================
# SECTION 5: Did cooldown PREVENT any of those bad days?
# =============================================================================
print("\n" + "=" * 110)
print("SECTION 5: HEEFT COOLDOWN DE SLECHTE DAGEN VOORKOMEN?")
print("=" * 110)

# For each scenario, check if the warning/halt days improved
for label, stats, delta_pct in results:
    if stats['n_blocked'] == 0:
        continue
    if label not in ["2d / 1.0% / alle", "3d / 1% / R<0.5", "3d / 1% / R<0.2", "5d / 1.0% / alle"]:
        continue

    scenario_daily = stats['daily_df']

    print(f"\n--- {label} (blocked {stats['n_blocked']} trades, P&L Δ={delta_pct:+.1f}%) ---")

    # Compare bad days
    if len(warning_days) > 0:
        print(f"\n  Impact op de slechte dagen uit baseline:")
        print(f"  {'Date':<12} {'Base P&L':>12} {'Base%':>7} {'Scenario P&L':>14} {'Scen%':>7} {'Δ P&L':>12}")
        print(f"  " + "-" * 75)

        for _, base_day in warning_days.iterrows():
            scen_day = scenario_daily[scenario_daily['date'] == base_day['date']]
            if len(scen_day) > 0:
                scen_pnl = scen_day.iloc[0]['pnl']
                scen_pct = scen_day.iloc[0]['daily_loss_pct']
                delta = scen_pnl - base_day['pnl']
                print(f"  {base_day['date']:<12} ${base_day['pnl']:>10,.2f} {base_day['daily_loss_pct']:>6.2f}% "
                      f"${scen_pnl:>12,.2f} {scen_pct:>6.2f}% ${delta:>10,.2f}")
            else:
                print(f"  {base_day['date']:<12} ${base_day['pnl']:>10,.2f} {base_day['daily_loss_pct']:>6.2f}% "
                      f"{'no trades':>14} {'N/A':>7} {'N/A':>12}")

# =============================================================================
# SECTION 6: Year-by-year breakdown
# =============================================================================
print("\n" + "=" * 110)
print("SECTION 6: JAAR-VOOR-JAAR BREAKDOWN 2015-2017")
print("=" * 110)

for year in [2015, 2016, 2017]:
    year_trades = trades_period[
        (trades_period['open_time'] >= f'{year}-01-01') &
        (trades_period['open_time'] < f'{year+1}-01-01')
    ]

    if len(year_trades) == 0:
        continue

    year_baseline = simulate_with_daily_safety(year_trades, cooldown_days=0)

    print(f"\n--- {year} ---")
    print(f"  Trades: {year_baseline['n_kept']}, P&L: ${year_baseline['kept_pnl']:,.2f}")
    print(f"  Safety hits: W={year_baseline['n_warning']} R={year_baseline['n_reduce']} "
          f"H={year_baseline['n_halt']} M={year_baseline['n_max']}")

    print(f"  {'Scenario':<22} {'Trades':>7} {'Blckd':>6} {'P&L':>12} {'ΔP&L%':>7} "
          f"{'Warn':>5} {'Reduce':>7} {'HALT':>5} {'MAX':>4}")
    print(f"  " + "-" * 90)

    for label, days, price, low_r, r_thresh in scenarios:
        stats = simulate_with_daily_safety(year_trades, days, price, low_r, r_thresh)
        d_pct = (stats['kept_pnl'] - year_baseline['kept_pnl']) / year_baseline['kept_pnl'] * 100 if year_baseline['kept_pnl'] != 0 else 0
        marker = " <+" if d_pct > 0 else ""
        print(f"  {label:<22} {stats['n_kept']:>7} {stats['n_blocked']:>6} ${stats['kept_pnl']:>10,.0f} {d_pct:>+6.1f}% "
              f"{stats['n_warning']:>5} {stats['n_reduce']:>7} {stats['n_halt']:>5} {stats['n_max']:>4}{marker}")

# =============================================================================
# FINAL
# =============================================================================
print("\n" + "=" * 110)
print("EINDOORDEEL 2015-2017")
print("=" * 110)

# Find if any scenario is positive
positive = [(l, s, d) for l, s, d in results if d > 0.1]
if positive:
    print("\nScenario's die MEER opleveren dan baseline:")
    for label, stats, delta in positive:
        print(f"  {label}: {delta:+.1f}% P&L, "
              f"W={stats['n_warning']} R={stats['n_reduce']} H={stats['n_halt']} M={stats['n_max']}")
else:
    print("\nGEEN ENKEL scenario levert meer op dan baseline.")
    print("Cooldown is OOK in 2015-2017 niet winstgevend.")

print(f"\nSafety tier impact samenvatting:")
b = baseline
print(f"  Baseline: {b['n_warning']} warning days, {b['n_reduce']} reduce days, "
      f"{b['n_halt']} halt days, {b['n_max']} max-loss days")

# Find the scenario with fewest halt days
min_halt = min(results, key=lambda x: x[1]['n_halt'])
print(f"  Minste HALT days: {min_halt[0]} -> {min_halt[1]['n_halt']} halt days "
      f"(P&L: {min_halt[2]:+.1f}%)")

min_warn = min(results, key=lambda x: x[1]['n_warning'])
print(f"  Minste WARNING days: {min_warn[0]} -> {min_warn[1]['n_warning']} warning days "
      f"(P&L: {min_warn[2]:+.1f}%)")
