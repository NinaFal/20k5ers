#!/usr/bin/env python3
"""
Impact analysis: What happens to total P&L if we block re-entries?
Simulates different cooldown scenarios.
"""

import pandas as pd
import numpy as np

pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 140)

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
    final_close_price = last_row['close_price']
    final_close_time = last_row['close_time']

    if direction == 'buy':
        risk_distance = abs(entry_price - sl)
        move_distance = final_close_price - entry_price
    else:
        risk_distance = abs(sl - entry_price)
        move_distance = entry_price - final_close_price

    final_r = move_distance / risk_distance if risk_distance > 0 else 0

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
    })

trades = pd.DataFrame(trade_list)
trades['open_time'] = pd.to_datetime(trades['open_time'], utc=True)
trades['close_time'] = pd.to_datetime(trades['close_time'], utc=True)
trades = trades.sort_values('open_time').reset_index(drop=True)

total_pnl_baseline = trades['total_pnl'].sum()
total_trades_baseline = len(trades)

print("=" * 110)
print("COOLDOWN IMPACT ANALYSIS: Wat gebeurt er als we re-entries blokkeren?")
print("=" * 110)
print(f"\nBaseline: {total_trades_baseline} trades, totaal P&L: ${total_pnl_baseline:,.2f}")
print(f"Gemiddeld per trade: ${total_pnl_baseline/total_trades_baseline:,.2f}")

# =============================================================================
# SIMULATE COOLDOWN: block a trade if same symbol+direction was closed
# within the last N days AND entry price is within X% of previous entry
# =============================================================================

def simulate_cooldown(trades_df, cooldown_days, price_threshold_pct,
                      only_after_low_r=False, low_r_threshold=0.5,
                      only_after_tp1=False):
    """
    Simulate what happens if we block re-entries.
    Returns (kept_trades, blocked_trades).
    """
    trades_sorted = trades_df.sort_values('open_time').reset_index(drop=True)
    kept = []
    blocked = []

    # Track last close per (symbol, direction)
    recent_closes = {}  # (symbol, direction) -> list of {close_time, entry_price, final_r, tp1_hit}

    for _, trade in trades_sorted.iterrows():
        key = (trade['symbol'], trade['direction'])
        should_block = False

        if key in recent_closes:
            for prev in recent_closes[key]:
                # Check time window
                time_diff = (trade['open_time'] - prev['close_time']).total_seconds() / 86400
                if time_diff < 0 or time_diff > cooldown_days:
                    continue

                # Check price similarity
                price_diff = abs(trade['entry_price'] - prev['entry_price']) / prev['entry_price'] * 100
                if price_diff > price_threshold_pct:
                    continue

                # Optional: only block after low R trades
                if only_after_low_r and prev['final_r'] >= low_r_threshold:
                    continue

                # Optional: only block after TP1 hit
                if only_after_tp1 and not prev['tp1_hit']:
                    continue

                should_block = True
                break

        if should_block:
            blocked.append(trade)
        else:
            kept.append(trade)
            # Add to recent closes
            if key not in recent_closes:
                recent_closes[key] = []
            recent_closes[key].append({
                'close_time': trade['close_time'],
                'entry_price': trade['entry_price'],
                'final_r': trade['final_r'],
                'tp1_hit': trade['tp1_hit'],
            })
            # Cleanup old entries
            cutoff = trade['open_time'] - pd.Timedelta(days=cooldown_days + 1)
            recent_closes[key] = [x for x in recent_closes[key]
                                  if x['close_time'] > cutoff]
        # Also add blocked trades to recent_closes for tracking
        # (the original trade still happened, we just wouldn't take re-entry)
        if should_block:
            if key not in recent_closes:
                recent_closes[key] = []
            # Don't add blocked trades - they wouldn't have been taken

    return pd.DataFrame(kept), pd.DataFrame(blocked)


# =============================================================================
# SCENARIO 1: Universal cooldown (all trades)
# =============================================================================
print("\n" + "=" * 110)
print("SCENARIO 1: Universele cooldown - blokkeer ALLE re-entries op dezelfde prijs")
print("=" * 110)

print(f"\n{'Cooldown':>10} {'Price%':>7} {'Blocked':>8} {'Blocked%':>9} "
      f"{'Blocked P&L':>14} {'Kept P&L':>14} {'Δ P&L':>14} {'Δ%':>8} "
      f"{'Blk Avg P&L':>12} {'Blk Win%':>9}")
print("-" * 120)

for days in [1, 2, 3, 5, 7]:
    for price_pct in [0.5, 1.0, 2.0]:
        kept, blocked = simulate_cooldown(trades, days, price_pct)
        if len(blocked) > 0:
            kept_pnl = kept['total_pnl'].sum()
            blocked_pnl = blocked['total_pnl'].sum()
            delta = kept_pnl - total_pnl_baseline
            delta_pct = delta / total_pnl_baseline * 100
            blk_avg = blocked_pnl / len(blocked)
            blk_win = (blocked['final_r'] > 0).mean() * 100
            print(f"{days:>8}d {price_pct:>6.1f}% {len(blocked):>8} {len(blocked)/len(trades)*100:>8.1f}% "
                  f"${blocked_pnl:>12,.2f} ${kept_pnl:>12,.2f} ${delta:>12,.2f} {delta_pct:>7.2f}% "
                  f"${blk_avg:>10,.2f} {blk_win:>8.1f}%")

# =============================================================================
# SCENARIO 2: Cooldown alleen na "disappointing" trades (TP1 hit, R < 0.5)
# =============================================================================
print("\n" + "=" * 110)
print("SCENARIO 2: Cooldown ALLEEN na disappointing trades (TP1 hit, final R < 0.5)")
print("=" * 110)

print(f"\n{'Cooldown':>10} {'Price%':>7} {'Blocked':>8} {'Blocked%':>9} "
      f"{'Blocked P&L':>14} {'Kept P&L':>14} {'Δ P&L':>14} {'Δ%':>8} "
      f"{'Blk Avg P&L':>12} {'Blk Win%':>9}")
print("-" * 120)

for days in [1, 2, 3, 5, 7]:
    for price_pct in [0.5, 1.0, 2.0]:
        kept, blocked = simulate_cooldown(trades, days, price_pct,
                                          only_after_low_r=True, low_r_threshold=0.5,
                                          only_after_tp1=True)
        if len(blocked) > 0:
            kept_pnl = kept['total_pnl'].sum()
            blocked_pnl = blocked['total_pnl'].sum()
            delta = kept_pnl - total_pnl_baseline
            delta_pct = delta / total_pnl_baseline * 100
            blk_avg = blocked_pnl / len(blocked)
            blk_win = (blocked['final_r'] > 0).mean() * 100
            print(f"{days:>8}d {price_pct:>6.1f}% {len(blocked):>8} {len(blocked)/len(trades)*100:>8.1f}% "
                  f"${blocked_pnl:>12,.2f} ${kept_pnl:>12,.2f} ${delta:>12,.2f} {delta_pct:>7.2f}% "
                  f"${blk_avg:>10,.2f} {blk_win:>8.1f}%")

# =============================================================================
# SCENARIO 3: Cooldown alleen na breakeven (R < 0.2)
# =============================================================================
print("\n" + "=" * 110)
print("SCENARIO 3: Cooldown ALLEEN na breakeven close (final R < 0.2)")
print("=" * 110)

print(f"\n{'Cooldown':>10} {'Price%':>7} {'Blocked':>8} {'Blocked%':>9} "
      f"{'Blocked P&L':>14} {'Kept P&L':>14} {'Δ P&L':>14} {'Δ%':>8} "
      f"{'Blk Avg P&L':>12} {'Blk Win%':>9}")
print("-" * 120)

for days in [1, 2, 3, 5, 7]:
    for price_pct in [0.5, 1.0, 2.0]:
        kept, blocked = simulate_cooldown(trades, days, price_pct,
                                          only_after_low_r=True, low_r_threshold=0.2)
        if len(blocked) > 0:
            kept_pnl = kept['total_pnl'].sum()
            blocked_pnl = blocked['total_pnl'].sum()
            delta = kept_pnl - total_pnl_baseline
            delta_pct = delta / total_pnl_baseline * 100
            blk_avg = blocked_pnl / len(blocked)
            blk_win = (blocked['final_r'] > 0).mean() * 100
            print(f"{days:>8}d {price_pct:>6.1f}% {len(blocked):>8} {len(blocked)/len(trades)*100:>8.1f}% "
                  f"${blocked_pnl:>12,.2f} ${kept_pnl:>12,.2f} ${delta:>12,.2f} {delta_pct:>7.2f}% "
                  f"${blk_avg:>10,.2f} {blk_win:>8.1f}%")

# =============================================================================
# SCENARIO 4: Cooldown alleen na verlies (R < 0)
# =============================================================================
print("\n" + "=" * 110)
print("SCENARIO 4: Cooldown ALLEEN na verlies (final R < 0)")
print("=" * 110)

print(f"\n{'Cooldown':>10} {'Price%':>7} {'Blocked':>8} {'Blocked%':>9} "
      f"{'Blocked P&L':>14} {'Kept P&L':>14} {'Δ P&L':>14} {'Δ%':>8} "
      f"{'Blk Avg P&L':>12} {'Blk Win%':>9}")
print("-" * 120)

for days in [1, 2, 3, 5, 7]:
    for price_pct in [0.5, 1.0, 2.0]:
        kept, blocked = simulate_cooldown(trades, days, price_pct,
                                          only_after_low_r=True, low_r_threshold=0.0)
        if len(blocked) > 0:
            kept_pnl = kept['total_pnl'].sum()
            blocked_pnl = blocked['total_pnl'].sum()
            delta = kept_pnl - total_pnl_baseline
            delta_pct = delta / total_pnl_baseline * 100
            blk_avg = blocked_pnl / len(blocked)
            blk_win = (blocked['final_r'] > 0).mean() * 100
            print(f"{days:>8}d {price_pct:>6.1f}% {len(blocked):>8} {len(blocked)/len(trades)*100:>8.1f}% "
                  f"${blocked_pnl:>12,.2f} ${kept_pnl:>12,.2f} ${delta:>12,.2f} {delta_pct:>7.2f}% "
                  f"${blk_avg:>10,.2f} {blk_win:>8.1f}%")

# =============================================================================
# SCENARIO 5: Per-symbol breakdown for best scenario
# =============================================================================
print("\n" + "=" * 110)
print("SCENARIO 5: Per-symbol impact (3d cooldown, 1% price, na breakeven R<0.2)")
print("=" * 110)

kept, blocked = simulate_cooldown(trades, 3, 1.0,
                                  only_after_low_r=True, low_r_threshold=0.2)

if len(blocked) > 0:
    sym_impact = blocked.groupby('symbol').agg(
        n_blocked=('base_ticket', 'count'),
        blocked_pnl=('total_pnl', 'sum'),
        avg_blocked_pnl=('total_pnl', 'mean'),
        avg_r=('final_r', 'mean'),
        win_pct=('final_r', lambda x: (x > 0).mean() * 100),
    ).sort_values('blocked_pnl')

    print(f"\n{'Symbol':<12} {'Blocked':>8} {'Blocked P&L':>14} {'Avg P&L':>12} {'Avg R':>8} {'Win%':>7} {'Verdict':>10}")
    print("-" * 80)
    for sym, row in sym_impact.iterrows():
        verdict = "SKIP" if row['blocked_pnl'] > 0 else "BLOCK OK"
        print(f"{sym:<12} {int(row['n_blocked']):>8} ${row['blocked_pnl']:>12,.2f} "
              f"${row['avg_blocked_pnl']:>10,.2f} {row['avg_r']:>8.3f} {row['win_pct']:>6.1f}% {verdict:>10}")

    # Summary
    profitable_blocked = blocked[blocked['total_pnl'] > 0]
    losing_blocked = blocked[blocked['total_pnl'] <= 0]
    print(f"\n  Geblokkeerde trades die winstgevend zouden zijn: {len(profitable_blocked)} "
          f"(${profitable_blocked['total_pnl'].sum():,.2f})")
    print(f"  Geblokkeerde trades die verliesgevend zouden zijn: {len(losing_blocked)} "
          f"(${losing_blocked['total_pnl'].sum():,.2f})")
    print(f"  Netto impact van blokkeren: ${-blocked['total_pnl'].sum():,.2f}")

# =============================================================================
# SCENARIO 6: Halve positie i.p.v. volledig blokkeren
# =============================================================================
print("\n" + "=" * 110)
print("SCENARIO 6: HALVE POSITIE bij re-entry i.p.v. volledig blokkeren")
print("=" * 110)

print(f"\n{'Cooldown':>10} {'Price%':>7} {'Affected':>9} "
      f"{'Full P&L':>14} {'Half P&L':>14} {'Δ P&L':>14} {'Δ%':>8}")
print("-" * 90)

for days in [1, 2, 3, 5]:
    for price_pct in [0.5, 1.0]:
        kept, blocked = simulate_cooldown(trades, days, price_pct,
                                          only_after_low_r=True, low_r_threshold=0.2)
        if len(blocked) > 0:
            # Half position = keep half the P&L of blocked trades
            half_pnl = kept['total_pnl'].sum() + blocked['total_pnl'].sum() * 0.5
            full_block_pnl = kept['total_pnl'].sum()
            delta_half = half_pnl - total_pnl_baseline
            delta_half_pct = delta_half / total_pnl_baseline * 100
            print(f"{days:>8}d {price_pct:>6.1f}% {len(blocked):>9} "
                  f"${full_block_pnl:>12,.2f} ${half_pnl:>12,.2f} ${delta_half:>12,.2f} {delta_half_pct:>7.2f}%")

# =============================================================================
# FINAL VERDICT
# =============================================================================
print("\n" + "=" * 110)
print("EINDOORDEEL")
print("=" * 110)

# Run the most reasonable scenarios and compare
scenarios = []
for label, days, price, low_r, r_thresh, tp1_only in [
    ("Geen cooldown (baseline)", 0, 0, False, 0, False),
    ("1d / 1% / alle trades", 1, 1.0, False, 0, False),
    ("2d / 1% / alle trades", 2, 1.0, False, 0, False),
    ("3d / 1% / alle trades", 3, 1.0, False, 0, False),
    ("1d / 1% / na R<0.5+TP1", 1, 1.0, True, 0.5, True),
    ("2d / 1% / na R<0.5+TP1", 2, 1.0, True, 0.5, True),
    ("3d / 1% / na R<0.5+TP1", 3, 1.0, True, 0.5, True),
    ("1d / 1% / na R<0.2", 1, 1.0, True, 0.2, False),
    ("2d / 1% / na R<0.2", 2, 1.0, True, 0.2, False),
    ("3d / 1% / na R<0.2", 3, 1.0, True, 0.2, False),
    ("1d / 1% / na verlies", 1, 1.0, True, 0.0, False),
    ("2d / 1% / na verlies", 2, 1.0, True, 0.0, False),
    ("3d / 1% / na verlies", 3, 1.0, True, 0.0, False),
]:
    if days == 0:
        scenarios.append((label, total_trades_baseline, total_pnl_baseline, 0, 0))
        continue

    kept, blocked = simulate_cooldown(trades, days, price,
                                      only_after_low_r=low_r, low_r_threshold=r_thresh,
                                      only_after_tp1=tp1_only)
    if len(blocked) > 0:
        kept_pnl = kept['total_pnl'].sum()
        delta = kept_pnl - total_pnl_baseline
        delta_pct = delta / total_pnl_baseline * 100
        scenarios.append((label, len(kept), kept_pnl, len(blocked), delta_pct))

print(f"\n{'Scenario':<30} {'Trades':>7} {'P&L':>16} {'Blocked':>8} {'Δ P&L%':>8}")
print("-" * 75)
for label, n_trades, pnl, n_blocked, delta_pct in scenarios:
    marker = " ***" if delta_pct > 0 else ""
    print(f"{label:<30} {n_trades:>7} ${pnl:>14,.2f} {n_blocked:>8} {delta_pct:>+7.2f}%{marker}")

print(f"\n*** = scenario dat meer oplevert dan baseline (cooldown = winstgevend)")
print(f"\nAls GEEN scenario positief is, is een cooldown mechanisme NIET winstgevend")
print(f"en zouden re-entries gewoon doorgelaten moeten worden.")
