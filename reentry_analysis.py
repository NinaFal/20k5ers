#!/usr/bin/env python3
"""
Re-entry Analysis: Do trades that hit TP1 but close at breakeven/small R
get re-entered on the same pair within 1-5 days at ~same entry price?
"""

import pandas as pd
import numpy as np

pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 140)
pd.set_option('display.float_format', lambda x: f'{x:,.2f}')

# =============================================================================
# LOAD DATA
# =============================================================================
df = pd.read_csv('/home/user/20k5ers/ftmo_analysis_output/backtest_2015_2025/trades.csv')
df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
df['close_time'] = pd.to_datetime(df['close_time'], utc=True)

# Parse base ticket and partial flag
df['base_ticket'] = df['ticket'].str.extract(r'^(\d+)')[0]
df['is_partial'] = df['ticket'].str.contains('_partial_')

print("=" * 100)
print("RE-ENTRY ANALYSIS: TP1 HIT → BREAKEVEN CLOSE → SAME TRADE RE-OPENED?")
print("=" * 100)

# =============================================================================
# SECTION 1: GROUP TRADES BY BASE TICKET
# =============================================================================
# For each base_ticket, reconstruct the full trade lifecycle
trade_groups = []

for base_id, group in df.groupby('base_ticket'):
    group = group.sort_values('close_time')

    partials = group[group['is_partial']]
    final = group[~group['is_partial']]

    symbol = group['symbol'].iloc[0]
    direction = group['type'].iloc[0]
    entry_price = group['open_price'].iloc[0]
    open_time = group['open_time'].iloc[0]
    sl = group['sl'].iloc[0]  # Original SL

    # Total PnL across all partial + final closes
    total_pnl = group['pnl'].sum()
    total_volume = group['volume'].sum()

    # Number of partial closes (= TP levels hit)
    n_partials = len(partials)
    tp1_hit = n_partials >= 1

    # Final close details
    if len(final) > 0:
        final_row = final.iloc[-1]
        final_close_price = final_row['close_price']
        final_close_time = final_row['close_time']
        final_pnl = final_row['pnl']
        final_volume = final_row['volume']
        final_sl = final_row['sl']  # SL at time of final close (may have moved to BE)
    else:
        # All partials, no "final" close row -> fully closed via partials
        final_row = partials.iloc[-1]
        final_close_price = final_row['close_price']
        final_close_time = final_row['close_time']
        final_pnl = final_row['pnl']
        final_volume = final_row['volume']
        final_sl = final_row['sl']

    # Calculate R-multiple for the trade
    # R = risk = distance from entry to original SL
    if direction == 'buy':
        risk_distance = abs(entry_price - sl)
        move_distance = final_close_price - entry_price
    else:  # sell
        risk_distance = abs(sl - entry_price)
        move_distance = entry_price - final_close_price

    if risk_distance > 0:
        total_r = move_distance / risk_distance  # R of final close price
        # Also compute R for the total trade PnL
        # But let's use the price-based R for the final portion
    else:
        total_r = 0

    # Detect breakeven close: SL moved to entry (within small tolerance)
    sl_at_breakeven = abs(final_sl - entry_price) / entry_price < 0.001  # 0.1% tolerance

    # Detect if final portion closed near breakeven (small R)
    final_r_close = total_r  # R at which the remaining position closed

    trade_groups.append({
        'base_ticket': base_id,
        'symbol': symbol,
        'direction': direction,
        'entry_price': entry_price,
        'open_time': open_time,
        'close_time': final_close_time,
        'original_sl': sl,
        'final_sl': final_sl,
        'final_close_price': final_close_price,
        'total_pnl': total_pnl,
        'final_pnl': final_pnl,
        'n_partials': n_partials,
        'tp1_hit': tp1_hit,
        'risk_distance': risk_distance,
        'final_r': final_r_close,
        'sl_at_breakeven': sl_at_breakeven,
        'total_volume': total_volume,
    })

trades = pd.DataFrame(trade_groups)
trades['open_time'] = pd.to_datetime(trades['open_time'], utc=True)
trades['close_time'] = pd.to_datetime(trades['close_time'], utc=True)

print(f"\nTotal unique trades (base tickets): {len(trades)}")
print(f"Trades with TP1 hit: {trades['tp1_hit'].sum()} ({trades['tp1_hit'].mean()*100:.1f}%)")
print(f"Trades with SL moved to BE: {trades['sl_at_breakeven'].sum()}")

# =============================================================================
# SECTION 2: IDENTIFY "TP1 HIT + CLOSE AT BREAKEVEN/LOW R" TRADES
# =============================================================================
print("\n" + "=" * 100)
print("SECTION 1: TRADES THAT HIT TP1 BUT CLOSED AT LOW R (breakeven/small profit)")
print("=" * 100)

# Define categories:
# - TP1 hit + final close at BE (R ~ 0): SL moved to breakeven, hit SL
# - TP1 hit + final close at low R (0 < R < 0.5): trailed but not much
# - TP1 hit + close at negative R: shouldn't happen if SL at BE, but let's check

tp1_trades = trades[trades['tp1_hit']].copy()
print(f"\nTrades that hit TP1: {len(tp1_trades)}")

# Categorize final R
def categorize_final_r(r):
    if r < -0.1:
        return 'Negative (< -0.1R)'
    elif r < 0.1:
        return 'Breakeven (-0.1R to 0.1R)'
    elif r < 0.5:
        return 'Low R (0.1R to 0.5R)'
    elif r < 1.0:
        return 'Medium R (0.5R to 1.0R)'
    else:
        return 'High R (>1.0R)'

tp1_trades['r_category'] = tp1_trades['final_r'].apply(categorize_final_r)

print("\n--- Final R distribution for TP1-hit trades ---")
cat_counts = tp1_trades['r_category'].value_counts()
for cat in ['Negative (< -0.1R)', 'Breakeven (-0.1R to 0.1R)', 'Low R (0.1R to 0.5R)',
            'Medium R (0.5R to 1.0R)', 'High R (>1.0R)']:
    if cat in cat_counts.index:
        count = cat_counts[cat]
        pct = count / len(tp1_trades) * 100
        avg_pnl = tp1_trades[tp1_trades['r_category'] == cat]['total_pnl'].mean()
        print(f"  {cat:35s}: {count:5d} ({pct:5.1f}%)  Avg total P&L: ${avg_pnl:>10,.2f}")

print(f"\n--- Final R statistics (TP1-hit trades) ---")
print(f"  Mean final R:   {tp1_trades['final_r'].mean():.3f}")
print(f"  Median final R: {tp1_trades['final_r'].median():.3f}")
print(f"  Std final R:    {tp1_trades['final_r'].std():.3f}")

# The "disappointing" trades: hit TP1 but closed at low R
disappointing = tp1_trades[tp1_trades['final_r'] < 0.5].copy()
print(f"\n'Disappointing' trades (TP1 hit but final R < 0.5): {len(disappointing)} ({len(disappointing)/len(tp1_trades)*100:.1f}% of TP1 trades)")
print(f"  Total P&L of these trades: ${disappointing['total_pnl'].sum():,.2f}")
print(f"  Average P&L: ${disappointing['total_pnl'].mean():,.2f}")

# =============================================================================
# SECTION 3: RE-ENTRY DETECTION
# =============================================================================
print("\n" + "=" * 100)
print("SECTION 2: RE-ENTRY DETECTION - Same pair, similar price, within 1-5 days")
print("=" * 100)

# For each "disappointing" trade, look for the next trade on the same pair
# within 1-5 days, in the same direction, at a similar entry price

reentries = []

for idx, dtrade in disappointing.iterrows():
    close_time = dtrade['close_time']
    symbol = dtrade['symbol']
    direction = dtrade['direction']
    entry_price = dtrade['entry_price']

    # Find next trades on same symbol within 1-5 days
    mask = (
        (trades['symbol'] == symbol) &
        (trades['open_time'] > close_time) &
        (trades['open_time'] <= close_time + pd.Timedelta(days=5))
    )

    candidates = trades[mask].sort_values('open_time')

    if len(candidates) == 0:
        continue

    next_trade = candidates.iloc[0]

    # Calculate price difference as % of entry
    price_diff_pct = abs(next_trade['entry_price'] - entry_price) / entry_price * 100

    # Same direction?
    same_direction = next_trade['direction'] == direction

    days_gap = (next_trade['open_time'] - close_time).total_seconds() / 86400

    reentries.append({
        'orig_ticket': dtrade['base_ticket'],
        'orig_symbol': symbol,
        'orig_direction': direction,
        'orig_entry_price': entry_price,
        'orig_final_r': dtrade['final_r'],
        'orig_total_pnl': dtrade['total_pnl'],
        'orig_close_time': close_time,
        'reentry_ticket': next_trade['base_ticket'],
        'reentry_direction': next_trade['direction'],
        'reentry_entry_price': next_trade['entry_price'],
        'reentry_open_time': next_trade['open_time'],
        'reentry_final_r': next_trade['final_r'],
        'reentry_total_pnl': next_trade['total_pnl'],
        'reentry_tp1_hit': next_trade['tp1_hit'],
        'price_diff_pct': price_diff_pct,
        'same_direction': same_direction,
        'days_gap': days_gap,
    })

re_df = pd.DataFrame(reentries)

if len(re_df) == 0:
    print("\nNo re-entries found!")
else:
    print(f"\nTotal disappointing trades with a follow-up on same pair within 5 days: {len(re_df)}")
    print(f"Out of {len(disappointing)} disappointing trades ({len(re_df)/len(disappointing)*100:.1f}%)")

    # Filter: same direction + similar price (within 1%)
    same_dir = re_df[re_df['same_direction']]
    print(f"\n--- Same direction re-entries: {len(same_dir)} ({len(same_dir)/len(re_df)*100:.1f}%) ---")

    # Price similarity buckets
    print("\n--- Price similarity of re-entries (same direction) ---")
    for threshold, label in [(0.5, '<0.5%'), (1.0, '<1.0%'), (2.0, '<2.0%'), (5.0, '<5.0%')]:
        close_price = same_dir[same_dir['price_diff_pct'] < threshold]
        if len(close_price) > 0:
            print(f"  Within {label} of original entry: {len(close_price)} trades")
            print(f"    Avg re-entry P&L: ${close_price['reentry_total_pnl'].mean():>10,.2f}")
            print(f"    Avg re-entry R:   {close_price['reentry_final_r'].mean():.3f}")
            print(f"    TP1 hit rate:     {close_price['reentry_tp1_hit'].mean()*100:.1f}%")
            print(f"    Avg gap (days):   {close_price['days_gap'].mean():.1f}")

    # The "true re-entries": same direction, within 1% price, within 5 days
    true_reentries = same_dir[same_dir['price_diff_pct'] < 1.0].copy()

    print(f"\n{'='*100}")
    print(f"SECTION 3: TRUE RE-ENTRIES (same pair, same direction, <1% price diff, <5 days)")
    print(f"{'='*100}")
    print(f"\nTotal true re-entries: {len(true_reentries)}")

    if len(true_reentries) > 0:
        print(f"\n--- Performance of re-entry trades ---")
        print(f"  Average P&L:     ${true_reentries['reentry_total_pnl'].mean():>10,.2f}")
        print(f"  Total P&L:       ${true_reentries['reentry_total_pnl'].sum():>10,.2f}")
        print(f"  Average R:       {true_reentries['reentry_final_r'].mean():.3f}")
        print(f"  TP1 hit rate:    {true_reentries['reentry_tp1_hit'].mean()*100:.1f}%")
        print(f"  Win rate (R>0):  {(true_reentries['reentry_final_r'] > 0).mean()*100:.1f}%")

        print(f"\n--- Compared to original disappointing trades ---")
        print(f"  Orig avg P&L:    ${true_reentries['orig_total_pnl'].mean():>10,.2f}")
        print(f"  Orig avg R:      {true_reentries['orig_final_r'].mean():.3f}")

        print(f"\n--- Time gap distribution ---")
        print(f"  Mean gap:   {true_reentries['days_gap'].mean():.1f} days")
        print(f"  Median gap: {true_reentries['days_gap'].median():.1f} days")
        for d in [1, 2, 3, 4, 5]:
            count = ((true_reentries['days_gap'] >= d-1) & (true_reentries['days_gap'] < d)).sum()
            print(f"  Day {d}: {count} re-entries")

        print(f"\n--- By symbol (top 15) ---")
        sym_stats = true_reentries.groupby('orig_symbol').agg(
            count=('reentry_ticket', 'count'),
            avg_reentry_pnl=('reentry_total_pnl', 'mean'),
            total_reentry_pnl=('reentry_total_pnl', 'sum'),
            avg_reentry_r=('reentry_final_r', 'mean'),
            tp1_rate=('reentry_tp1_hit', 'mean'),
            avg_gap=('days_gap', 'mean'),
        ).sort_values('count', ascending=False).head(15)

        print(f"{'Symbol':<12} {'Count':>6} {'Avg P&L':>12} {'Total P&L':>14} {'Avg R':>8} {'TP1%':>6} {'Gap':>5}")
        print("-" * 70)
        for sym, row in sym_stats.iterrows():
            print(f"{sym:<12} {int(row['count']):>6} ${row['avg_reentry_pnl']:>10,.2f} ${row['total_reentry_pnl']:>12,.2f} "
                  f"{row['avg_reentry_r']:>8.3f} {row['tp1_rate']*100:>5.1f}% {row['avg_gap']:>4.1f}d")

        # Show some examples
        print(f"\n--- Sample re-entry sequences ---")
        samples = true_reentries.sort_values('days_gap').head(20)
        print(f"{'Symbol':<12} {'Dir':>5} {'Orig Entry':>12} {'Orig R':>7} {'Re-Entry':>12} {'Re R':>7} "
              f"{'Price Δ%':>8} {'Gap':>6} {'Re P&L':>10}")
        print("-" * 95)
        for _, row in samples.iterrows():
            print(f"{row['orig_symbol']:<12} {row['orig_direction']:>5} {row['orig_entry_price']:>12.5f} "
                  f"{row['orig_final_r']:>7.3f} {row['reentry_entry_price']:>12.5f} {row['reentry_final_r']:>7.3f} "
                  f"{row['price_diff_pct']:>7.2f}% {row['days_gap']:>5.1f}d ${row['reentry_total_pnl']:>9,.2f}")

    # =============================================================================
    # SECTION 4: ALSO CHECK OPPOSITE DIRECTION RE-ENTRIES
    # =============================================================================
    opp_dir = re_df[~re_df['same_direction']]
    print(f"\n{'='*100}")
    print(f"SECTION 4: OPPOSITE DIRECTION RE-ENTRIES (reversal trades)")
    print(f"{'='*100}")
    print(f"\nOpposite direction follow-ups within 5 days: {len(opp_dir)}")

    if len(opp_dir) > 0:
        opp_close = opp_dir[opp_dir['price_diff_pct'] < 1.0]
        print(f"Within 1% price: {len(opp_close)}")
        if len(opp_close) > 0:
            print(f"  Avg P&L: ${opp_close['reentry_total_pnl'].mean():,.2f}")
            print(f"  Avg R:   {opp_close['reentry_final_r'].mean():.3f}")
            print(f"  Win rate: {(opp_close['reentry_final_r'] > 0).mean()*100:.1f}%")

# =============================================================================
# SECTION 5: ALL RE-ENTRIES (not just disappointing)
# =============================================================================
print(f"\n{'='*100}")
print(f"SECTION 5: ALL CONSECUTIVE SAME-PAIR TRADES (any R, within 5 days)")
print(f"{'='*100}")

all_reentries = []

for idx, trade in trades.iterrows():
    close_time = trade['close_time']
    symbol = trade['symbol']
    direction = trade['direction']
    entry_price = trade['entry_price']

    mask = (
        (trades['symbol'] == symbol) &
        (trades['direction'] == direction) &
        (trades['open_time'] > close_time) &
        (trades['open_time'] <= close_time + pd.Timedelta(days=5))
    )

    candidates = trades[mask].sort_values('open_time')

    if len(candidates) == 0:
        continue

    next_trade = candidates.iloc[0]
    price_diff_pct = abs(next_trade['entry_price'] - entry_price) / entry_price * 100
    days_gap = (next_trade['open_time'] - close_time).total_seconds() / 86400

    all_reentries.append({
        'orig_ticket': trade['base_ticket'],
        'symbol': symbol,
        'direction': direction,
        'orig_entry': entry_price,
        'orig_r': trade['final_r'],
        'orig_pnl': trade['total_pnl'],
        'orig_tp1': trade['tp1_hit'],
        'orig_n_partials': trade['n_partials'],
        'reentry_entry': next_trade['entry_price'],
        'reentry_r': next_trade['final_r'],
        'reentry_pnl': next_trade['total_pnl'],
        'reentry_tp1': next_trade['tp1_hit'],
        'price_diff_pct': price_diff_pct,
        'days_gap': days_gap,
    })

all_re = pd.DataFrame(all_reentries)
similar_price = all_re[all_re['price_diff_pct'] < 1.0]

print(f"\nAll same-pair same-direction follow-ups within 5 days: {len(all_re)}")
print(f"With similar price (<1% diff): {len(similar_price)}")

if len(similar_price) > 0:
    print(f"\n--- Performance of 'similar price' re-entries ---")
    print(f"  Avg re-entry P&L: ${similar_price['reentry_pnl'].mean():,.2f}")
    print(f"  Total re-entry P&L: ${similar_price['reentry_pnl'].sum():,.2f}")
    print(f"  Avg re-entry R:   {similar_price['reentry_r'].mean():.3f}")
    print(f"  Win rate (R>0):   {(similar_price['reentry_r'] > 0).mean()*100:.1f}%")
    print(f"  TP1 hit rate:     {similar_price['reentry_tp1'].mean()*100:.1f}%")

    # Compare: original trade outcome vs re-entry outcome
    print(f"\n--- Original trade that preceded re-entry ---")
    print(f"  Avg orig P&L:  ${similar_price['orig_pnl'].mean():,.2f}")
    print(f"  Avg orig R:    {similar_price['orig_r'].mean():.3f}")
    print(f"  TP1 hit rate:  {similar_price['orig_tp1'].mean()*100:.1f}%")

    # Break down by original trade outcome
    print(f"\n--- Re-entry quality based on HOW the original trade closed ---")

    for label, mask_fn in [
        ("Orig R < 0 (loss)", lambda x: x['orig_r'] < 0),
        ("Orig 0 <= R < 0.3 (breakeven)", lambda x: (x['orig_r'] >= 0) & (x['orig_r'] < 0.3)),
        ("Orig 0.3 <= R < 0.8 (low R)", lambda x: (x['orig_r'] >= 0.3) & (x['orig_r'] < 0.8)),
        ("Orig R >= 0.8 (good R)", lambda x: x['orig_r'] >= 0.8),
    ]:
        subset = similar_price[mask_fn(similar_price)]
        if len(subset) > 0:
            print(f"\n  {label}: {len(subset)} re-entries")
            print(f"    Re-entry avg P&L: ${subset['reentry_pnl'].mean():>10,.2f}")
            print(f"    Re-entry avg R:   {subset['reentry_r'].mean():.3f}")
            print(f"    Re-entry win%:    {(subset['reentry_r'] > 0).mean()*100:.1f}%")
            print(f"    Re-entry TP1%:    {subset['reentry_tp1'].mean()*100:.1f}%")

    # By symbol
    print(f"\n--- Top symbols with most similar-price re-entries ---")
    sym_re = similar_price.groupby('symbol').agg(
        count=('orig_ticket', 'count'),
        avg_re_pnl=('reentry_pnl', 'mean'),
        total_re_pnl=('reentry_pnl', 'sum'),
        avg_re_r=('reentry_r', 'mean'),
        avg_orig_r=('orig_r', 'mean'),
        avg_gap=('days_gap', 'mean'),
    ).sort_values('count', ascending=False)

    print(f"{'Symbol':<12} {'Count':>6} {'Re Avg P&L':>12} {'Re Tot P&L':>14} {'Re Avg R':>9} {'Orig Avg R':>10} {'Gap':>5}")
    print("-" * 75)
    for sym, row in sym_re.iterrows():
        print(f"{sym:<12} {int(row['count']):>6} ${row['avg_re_pnl']:>10,.2f} ${row['total_re_pnl']:>12,.2f} "
              f"{row['avg_re_r']:>9.3f} {row['avg_orig_r']:>10.3f} {row['avg_gap']:>4.1f}d")

print(f"\n{'='*100}")
print("END OF RE-ENTRY ANALYSIS")
print(f"{'='*100}")
