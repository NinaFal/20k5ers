#!/usr/bin/env python3
"""
Entry Price Shift Analysis (2017-2022)

Tests the impact of shifting entry prices by 0.5%:
  Longs:  buy market/limit = 0.5% HIGHER (worse fill), buy stop = 0.5% LOWER (better trigger)
  Shorts: sell market/limit = 0.5% LOWER (worse fill),  sell stop = 0.5% HIGHER (better trigger)

For the golden pocket strategy:
  - Buys enter at GP below current price → mostly buy_limit
  - Sells enter at GP above current price → mostly sell_limit
  - Some entries near current price → market orders
  - Rare breakout entries → buy_stop / sell_stop
"""

import pandas as pd
import numpy as np

pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 140)

# =============================================================================
# LOAD DATA
# =============================================================================
df = pd.read_csv('/home/user/20k5ers/ftmo_analysis_output/backtest_2015_2025/trades.csv')
df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
df['close_time'] = pd.to_datetime(df['close_time'], utc=True)

# Filter 2017-2022
df = df[(df['open_time'] >= '2017-01-01') & (df['open_time'] < '2023-01-01')].copy()

# Reconstruct base trades (combine partials)
df['base_ticket'] = df['ticket'].str.extract(r'^(\d+)')[0]
df['is_partial'] = df['ticket'].str.contains('_partial_')

print("=" * 120)
print("ENTRY PRICE SHIFT ANALYSE: 2017-2022")
print("=" * 120)

# =============================================================================
# For each partial row, we can compute the pip_value_factor
# pip_value_factor = pnl / (price_move * volume)
# Then shift the entry and recalculate pnl
# =============================================================================

# Compute pip value factor per row
# For buys: pnl = (close - open) * volume * pip_value_factor
# For sells: pnl = (open - close) * volume * pip_value_factor
df['price_move'] = np.where(
    df['type'] == 'buy',
    df['close_price'] - df['open_price'],
    df['open_price'] - df['close_price']
)

# Avoid division by zero
df['pip_value_factor'] = np.where(
    (df['price_move'] != 0) & (df['volume'] != 0),
    df['pnl'] / (df['price_move'] * df['volume']),
    0
)

# For rows where price_move is very small (near-zero), use the symbol average
# Group by symbol to get typical pip_value_factor
symbol_pvf = df[df['price_move'].abs() > 0.0001].groupby('symbol')['pip_value_factor'].median()
print("\nPip value factors per symbol (median):")
for sym, pvf in symbol_pvf.items():
    print(f"  {sym}: {pvf:,.0f}")

# Fill near-zero-move rows with symbol median
for sym in df['symbol'].unique():
    mask = (df['symbol'] == sym) & (df['price_move'].abs() <= 0.0001)
    if mask.any() and sym in symbol_pvf:
        df.loc[mask, 'pip_value_factor'] = symbol_pvf[sym]


# =============================================================================
# Determine order type heuristic
# For the golden pocket strategy:
#   - Buy entries below current → buy_limit (vast majority)
#   - Sell entries above current → sell_limit (vast majority)
#   - We don't have current_price at signal time, but we know:
#     * Buy limit: entry < current → price had to DROP to fill → entry below close of signal bar
#     * Sell limit: entry > current → price had to RISE to fill → entry above close of signal bar
#   - We'll use a simple heuristic: compare entry to SL
#     * Buys: SL below entry. If entry is far from SL (large risk), likely buy_limit
#     * Buy stop would have entry above current → unusual for GP strategy
#   - For simplicity: assume ALL are limit orders (>95% true for GP strategy)
#     Then test separately with mixed assumption
# =============================================================================

SHIFT_PCT = 0.005  # 0.5%

def apply_entry_shift(df_in, shift_pct=SHIFT_PCT, all_limits=True):
    """
    Apply entry price shift and recalculate P&L.

    If all_limits=True: assume all are limit orders
      Buys: entry + 0.5% (worse)
      Sells: entry - 0.5% (worse)

    If all_limits=False: try to detect order type
      Buy limit (entry < close at open_time): entry + 0.5%
      Buy stop (entry > close at open_time): entry - 0.5%
      Sell limit (entry > close at open_time): entry - 0.5%
      Sell stop (entry < close at open_time): entry + 0.5%
    """
    out = df_in.copy()

    if all_limits:
        # Longs: buy limit → 0.5% higher (worse)
        # Shorts: sell limit → 0.5% lower (worse)
        out['new_open_price'] = np.where(
            out['type'] == 'buy',
            out['open_price'] * (1 + shift_pct),   # buy higher = worse
            out['open_price'] * (1 - shift_pct),    # sell lower = worse
        )
    else:
        # Same as all_limits for now (we don't have stop order detection)
        out['new_open_price'] = np.where(
            out['type'] == 'buy',
            out['open_price'] * (1 + shift_pct),
            out['open_price'] * (1 - shift_pct),
        )

    # Entry shift in price
    out['entry_shift'] = out['new_open_price'] - out['open_price']

    # New P&L:
    # Buy: new_pnl = (close - new_open) * vol * pvf
    #     = pnl + (open - new_open) * vol * pvf
    #     = pnl - entry_shift * vol * pvf
    # Sell: new_pnl = (new_open - close) * vol * pvf
    #     = pnl + (new_open - open) * vol * pvf
    #     = pnl + entry_shift * vol * pvf
    out['pnl_delta'] = np.where(
        out['type'] == 'buy',
        -out['entry_shift'] * out['volume'] * out['pip_value_factor'],
        out['entry_shift'] * out['volume'] * out['pip_value_factor'],
    )

    out['new_pnl'] = out['pnl'] + out['pnl_delta']

    # Check if entry now beyond SL (trade would be invalid)
    # Buy: new_entry must be > SL (buy above stop loss)
    # Sell: new_entry must be < SL (sell below stop loss)
    out['entry_beyond_sl'] = np.where(
        out['type'] == 'buy',
        out['new_open_price'] <= out['sl'],  # entry dropped below SL
        out['new_open_price'] >= out['sl'],  # entry above SL
    )

    return out


# =============================================================================
# TEST DIFFERENT SHIFT LEVELS
# =============================================================================
print("\n" + "=" * 120)
print("SHIFT IMPACT OP P&L (alle trades als limit orders)")
print("=" * 120)

shifts = [0.001, 0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02]

baseline_pnl = df['pnl'].sum()
n_trades = len(df)
print(f"\nBaseline: {n_trades} rows, P&L: ${baseline_pnl:,.2f}")

# Group by base_ticket for trade-level stats
trade_level = df.groupby('base_ticket').agg({
    'pnl': 'sum',
    'type': 'first',
    'symbol': 'first',
    'open_time': 'first',
    'open_price': 'first',
    'sl': 'first',
}).reset_index()
n_base_trades = len(trade_level)
print(f"Unique trades: {n_base_trades}")

print(f"\n{'Shift':>8} {'New P&L':>14} {'ΔP&L':>12} {'ΔP&L%':>8} {'Invalid':>8} {'Per Trade':>12}")
print("-" * 75)

for shift in shifts:
    shifted = apply_entry_shift(df, shift_pct=shift)
    new_pnl = shifted['new_pnl'].sum()
    delta = new_pnl - baseline_pnl
    delta_pct = delta / baseline_pnl * 100
    n_invalid = shifted['entry_beyond_sl'].sum()
    per_trade = delta / n_base_trades

    print(f"  {shift*100:5.2f}%  ${new_pnl:>12,.0f}  ${delta:>10,.0f}  {delta_pct:>+6.1f}%  {n_invalid:>7}  ${per_trade:>10,.2f}")


# =============================================================================
# YEAR-BY-YEAR ANALYSIS WITH 0.5% SHIFT
# =============================================================================
print("\n" + "=" * 120)
print("JAAR-VOOR-JAAR IMPACT (0.5% shift, limit orders)")
print("=" * 120)

shifted_05 = apply_entry_shift(df, shift_pct=0.005)

for year in range(2017, 2023):
    mask = (df['open_time'] >= f'{year}-01-01') & (df['open_time'] < f'{year+1}-01-01')
    year_base = df[mask]['pnl'].sum()
    year_new = shifted_05[mask]['new_pnl'].sum()
    year_delta = year_new - year_base
    year_n = df[mask].groupby('base_ticket').ngroups
    year_invalid = shifted_05[mask]['entry_beyond_sl'].sum()

    print(f"  {year}: Base ${year_base:>10,.0f} → Shifted ${year_new:>10,.0f} "
          f"(Δ ${year_delta:>8,.0f}, {year_delta/year_base*100 if year_base else 0:>+5.1f}%) "
          f"[{year_n} trades, {year_invalid} invalid]")


# =============================================================================
# PER-SYMBOL IMPACT
# =============================================================================
print("\n" + "=" * 120)
print("PER SYMBOOL IMPACT (0.5% shift)")
print("=" * 120)

print(f"\n{'Symbol':<12} {'Base P&L':>12} {'New P&L':>12} {'ΔP&L':>10} {'ΔP&L%':>8} {'Trades':>7}")
print("-" * 70)

for sym in sorted(df['symbol'].unique()):
    mask = df['symbol'] == sym
    base = df[mask]['pnl'].sum()
    new = shifted_05[mask]['new_pnl'].sum()
    delta = new - base
    n = df[mask].groupby('base_ticket').ngroups
    pct = delta / base * 100 if base != 0 else 0
    print(f"  {sym:<10} ${base:>10,.0f} ${new:>10,.0f} ${delta:>8,.0f} {pct:>+6.1f}% {n:>7}")


# =============================================================================
# WIN/LOSS IMPACT - Does 0.5% shift turn winners into losers?
# =============================================================================
print("\n" + "=" * 120)
print("WIN/LOSS IMPACT (0.5% shift)")
print("=" * 120)

# Trade-level analysis
trade_base = df.groupby('base_ticket').agg({
    'pnl': 'sum',
    'type': 'first',
    'symbol': 'first',
    'open_time': 'first',
}).reset_index()

trade_shifted = shifted_05.groupby('base_ticket').agg({
    'new_pnl': 'sum',
}).reset_index()

merged = trade_base.merge(trade_shifted, on='base_ticket')

base_winners = (merged['pnl'] > 0).sum()
base_losers = (merged['pnl'] <= 0).sum()
new_winners = (merged['new_pnl'] > 0).sum()
new_losers = (merged['new_pnl'] <= 0).sum()

# Trades that flipped
win_to_loss = ((merged['pnl'] > 0) & (merged['new_pnl'] <= 0)).sum()
loss_to_win = ((merged['pnl'] <= 0) & (merged['new_pnl'] > 0)).sum()

print(f"\n  Baseline:  {base_winners} winners / {base_losers} losers ({base_winners/len(merged)*100:.1f}% WR)")
print(f"  Shifted:   {new_winners} winners / {new_losers} losers ({new_winners/len(merged)*100:.1f}% WR)")
print(f"  Flipped W→L: {win_to_loss}")
print(f"  Flipped L→W: {loss_to_win}")


# =============================================================================
# R-MULTIPLE IMPACT - New risk distance affects R
# =============================================================================
print("\n" + "=" * 120)
print("RISK/R-MULTIPLE IMPACT (0.5% shift)")
print("=" * 120)

# For each base trade, compute original and new risk distance
trade_detail = df.groupby('base_ticket').agg({
    'open_price': 'first',
    'sl': 'first',
    'type': 'first',
    'pnl': 'sum',
    'close_price': 'last',
}).reset_index()

# Original risk
trade_detail['orig_risk'] = np.where(
    trade_detail['type'] == 'buy',
    trade_detail['open_price'] - trade_detail['sl'],
    trade_detail['sl'] - trade_detail['open_price']
)

# New entry
trade_detail['new_entry'] = np.where(
    trade_detail['type'] == 'buy',
    trade_detail['open_price'] * 1.005,
    trade_detail['open_price'] * 0.995,
)

# New risk distance
trade_detail['new_risk'] = np.where(
    trade_detail['type'] == 'buy',
    trade_detail['new_entry'] - trade_detail['sl'],
    trade_detail['sl'] - trade_detail['new_entry']
)

# Risk change
trade_detail['risk_change_pct'] = (trade_detail['new_risk'] - trade_detail['orig_risk']) / trade_detail['orig_risk'] * 100

valid = trade_detail[trade_detail['orig_risk'] > 0]

print(f"\n  Gemiddelde risico-afstand verandering: {valid['risk_change_pct'].mean():+.2f}%")
print(f"  Mediaan risico-afstand verandering:   {valid['risk_change_pct'].median():+.2f}%")
print(f"  Max risico toename: {valid['risk_change_pct'].max():+.2f}%")
print(f"  Max risico afname:  {valid['risk_change_pct'].min():+.2f}%")

# What this means for lot sizing
print(f"\n  Als lot size wordt aangepast aan nieuw risico:")
print(f"  → Gemiddeld {abs(valid['risk_change_pct'].mean()):.1f}% grotere risico-afstand")
print(f"  → Proportioneel kleinere lot sizes nodig")
print(f"  → Effectief minder exposure per trade")


# =============================================================================
# WHAT IF WE ADJUST LOT SIZE FOR NEW RISK?
# =============================================================================
print("\n" + "=" * 120)
print("SCENARIO: ENTRY SHIFT + HERBEREKENDE LOT SIZE")
print("=" * 120)

# If we adjust lot size to maintain same $ risk:
# new_lot = old_lot * (orig_risk / new_risk)
# Then: new_pnl = old_pnl * (orig_risk / new_risk) + lot_correction_effect

# For simplicity at the row level:
df_adj = shifted_05.copy()

# Merge risk info
risk_map = trade_detail.set_index('base_ticket')[['orig_risk', 'new_risk']].to_dict()
df_adj['orig_risk'] = df_adj['base_ticket'].map(risk_map.get('orig_risk', {}))
df_adj['new_risk'] = df_adj['base_ticket'].map(risk_map.get('new_risk', {}))

# Lot size adjustment factor
df_adj['lot_factor'] = np.where(
    (df_adj['new_risk'] > 0) & (df_adj['orig_risk'] > 0),
    df_adj['orig_risk'] / df_adj['new_risk'],
    1.0
)

# P&L with adjusted lot size
# new_pnl_adj = new_pnl * lot_factor
# But more precisely: with new entry and adjusted lot size:
# For buy: pnl_adj = (close - new_entry) * (old_vol * lot_factor) * pvf
#         = new_pnl * lot_factor  (approximately)
df_adj['new_pnl_adj'] = df_adj['new_pnl'] * df_adj['lot_factor']

adj_total = df_adj['new_pnl_adj'].sum()
raw_total = df_adj['new_pnl'].sum()
base_total = df_adj['pnl'].sum()

print(f"\n  Baseline P&L:             ${base_total:>12,.2f}")
print(f"  Shifted P&L (same lots):  ${raw_total:>12,.2f} ({(raw_total-base_total)/base_total*100:+.1f}%)")
print(f"  Shifted P&L (adj lots):   ${adj_total:>12,.2f} ({(adj_total-base_total)/base_total*100:+.1f}%)")

# Year by year with adjusted lots
print(f"\n  Per jaar (adjusted lots):")
for year in range(2017, 2023):
    mask = (df_adj['open_time'] >= f'{year}-01-01') & (df_adj['open_time'] < f'{year+1}-01-01')
    yb = df_adj[mask]['pnl'].sum()
    ya = df_adj[mask]['new_pnl_adj'].sum()
    print(f"    {year}: ${yb:>10,.0f} → ${ya:>10,.0f} ({(ya-yb)/yb*100 if yb else 0:>+5.1f}%)")


# =============================================================================
# WHAT IF ENTRY SHIFT WERE FAVORABLE? (The opposite)
# =============================================================================
print("\n" + "=" * 120)
print("BONUS: WAT ALS WE 0.5% BETERE ENTRIES KRIJGEN?")
print("=" * 120)

# Reverse: buys 0.5% lower, sells 0.5% higher
better = apply_entry_shift(df, shift_pct=-0.005)
better_pnl = better['new_pnl'].sum()
better_delta = better_pnl - baseline_pnl

print(f"\n  Baseline:     ${baseline_pnl:>12,.2f}")
print(f"  0.5% betere:  ${better_pnl:>12,.2f} ({better_delta/baseline_pnl*100:+.1f}%)")
print(f"  Verschil:     ${better_delta:>12,.2f}")
print(f"  Per trade:    ${better_delta/n_base_trades:>12,.2f}")

print(f"\n  Per jaar:")
for year in range(2017, 2023):
    mask = (df['open_time'] >= f'{year}-01-01') & (df['open_time'] < f'{year+1}-01-01')
    yb = df[mask]['pnl'].sum()
    yn = better[mask]['new_pnl'].sum()
    yd = yn - yb
    print(f"    {year}: ${yb:>10,.0f} → ${yn:>10,.0f} ({yd/yb*100 if yb else 0:>+5.1f}%)")


# =============================================================================
# DAILY SAFETY IMPACT
# =============================================================================
print("\n" + "=" * 120)
print("DAILY SAFETY IMPACT (0.5% shift)")
print("=" * 120)

from collections import defaultdict

ACCOUNT_SIZE = 20000.0

def compute_daily_safety(df_in, pnl_col='pnl'):
    daily = defaultdict(float)
    for _, row in df_in.iterrows():
        day = row['close_time'].strftime('%Y-%m-%d')
        daily[day] += row[pnl_col]

    results = {'warning': 0, 'reduce': 0, 'halt': 0, 'max': 0, 'worst': 0}
    for day, pnl in daily.items():
        loss_pct = max(0, -pnl) / ACCOUNT_SIZE * 100
        if loss_pct >= 2.0: results['warning'] += 1
        if loss_pct >= 3.0: results['reduce'] += 1
        if loss_pct >= 3.2: results['halt'] += 1
        if loss_pct >= 5.0: results['max'] += 1
        if pnl < results['worst']: results['worst'] = pnl
    return results

base_safety = compute_daily_safety(df)
shift_safety = compute_daily_safety(shifted_05, 'new_pnl')

print(f"\n  {'Metric':<25} {'Baseline':>10} {'0.5% Shift':>12} {'Verschil':>10}")
print(f"  " + "-" * 60)
for metric, label in [('warning', 'Warning (≥2%)'), ('reduce', 'Reduce (≥3%)'),
                        ('halt', 'HALT (≥3.2%)'), ('max', 'MAX LOSS (≥5%)')]:
    b = base_safety[metric]
    s = shift_safety[metric]
    print(f"  {label:<25} {b:>10} {s:>12} {s-b:>+10}")

print(f"  {'Worst day':<25} ${base_safety['worst']:>9,.0f} ${shift_safety['worst']:>11,.0f}")


# =============================================================================
# CONCLUSIE
# =============================================================================
print("\n" + "=" * 120)
print("CONCLUSIE")
print("=" * 120)

delta_pct = (raw_total - base_total) / base_total * 100
per_trade_cost = (raw_total - base_total) / n_base_trades

print(f"""
  0.5% slechtere entries (limit orders) voor 2017-2022:

  P&L impact:  ${raw_total - base_total:>10,.0f} ({delta_pct:+.1f}%)
  Per trade:   ${per_trade_cost:>10,.2f}

  {'De strategie is ROBUUST' if abs(delta_pct) < 10 else 'SIGNIFICANTE impact'}
  tegen 0.5% entry verschuiving.

  Entry precision kost/levert ~${abs(per_trade_cost):.0f} per trade.
""")
