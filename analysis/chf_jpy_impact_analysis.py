"""
Analyse: Impact van Currency Exposure Limiter op CHF & JPY trades
Simuleert wat er was gebeurd als we max N posities per currency hadden toegestaan.
"""
import pandas as pd
import json
from collections import defaultdict
from datetime import datetime

# Load trades
df = pd.read_csv('/workspaces/20k5ers/ftmo_analysis_output/SIMULATE_2023_2025_20K_JAN18/closed_trades.csv')
df['fill_time'] = pd.to_datetime(df['fill_time'])
df['exit_time'] = pd.to_datetime(df['exit_time'])

print("=" * 80)
print("CURRENCY EXPOSURE IMPACT ANALYSIS")
print("Laatste backtest: 2023-2025, $20K start")
print("=" * 80)

# ─── STAP 1: Basisanalyse CHF & JPY trades ───
def get_currencies(symbol):
    """Extract both currencies from a pair"""
    parts = symbol.split('_')
    if len(parts) == 2:
        return parts
    return [symbol]

chf_trades = df[df['symbol'].str.contains('CHF')]
jpy_trades = df[df['symbol'].str.contains('JPY')]

print(f"\n{'─'*60}")
print(f"TOTAAL TRADES: {len(df)}")
print(f"CHF trades: {len(chf_trades)} ({len(chf_trades)/len(df)*100:.1f}%)")
print(f"JPY trades: {len(jpy_trades)} ({len(jpy_trades)/len(df)*100:.1f}%)")
print(f"CHF+JPY (incl CHF_JPY overlap): {len(df[df['symbol'].str.contains('CHF|JPY')])}")

# Per symbol breakdown
print(f"\n{'─'*60}")
print("CHF PAIRS - Trade Count & Performance:")
print(f"{'Symbol':<15} {'Count':>6} {'Win%':>7} {'Avg R':>8} {'Total R':>9} {'Total PnL':>12}")
for sym in sorted(chf_trades['symbol'].unique()):
    subset = chf_trades[chf_trades['symbol'] == sym]
    wins = (subset['realized_r'] > 0).sum()
    wr = wins / len(subset) * 100 if len(subset) > 0 else 0
    avg_r = subset['realized_r'].mean()
    tot_r = subset['realized_r'].sum()
    tot_pnl = subset['realized_pnl'].sum()
    print(f"{sym:<15} {len(subset):>6} {wr:>6.1f}% {avg_r:>8.3f} {tot_r:>9.2f} {tot_pnl:>12.2f}")

print(f"\nJPY PAIRS - Trade Count & Performance:")
print(f"{'Symbol':<15} {'Count':>6} {'Win%':>7} {'Avg R':>8} {'Total R':>9} {'Total PnL':>12}")
for sym in sorted(jpy_trades['symbol'].unique()):
    subset = jpy_trades[jpy_trades['symbol'] == sym]
    wins = (subset['realized_r'] > 0).sum()
    wr = wins / len(subset) * 100 if len(subset) > 0 else 0
    avg_r = subset['realized_r'].mean()
    tot_r = subset['realized_r'].sum()
    tot_pnl = subset['realized_pnl'].sum()
    print(f"{sym:<15} {len(subset):>6} {wr:>6.1f}% {avg_r:>8.3f} {tot_r:>9.2f} {tot_pnl:>12.2f}")

# ─── STAP 2: Overlap analyse - hoeveel CHF/JPY open tegelijk? ───
print(f"\n{'='*80}")
print("OVERLAP ANALYSE: Hoeveel CHF/JPY trades tegelijk open?")
print(f"{'='*80}")

def count_concurrent_currency(df, currency):
    """Count max concurrent positions containing a specific currency"""
    events = []
    for _, row in df[df['symbol'].str.contains(currency)].iterrows():
        events.append((row['fill_time'], 1, row['symbol'], row['realized_r'], row['realized_pnl']))
        events.append((row['exit_time'], -1, row['symbol'], 0, 0))
    
    events.sort(key=lambda x: x[0])
    current = 0
    max_concurrent = 0
    concurrent_log = []
    
    for time, delta, sym, r, pnl in events:
        current += delta
        if current > max_concurrent:
            max_concurrent = current
            concurrent_log.append((time, current))
    
    # Build histogram
    histogram = defaultdict(int)
    for time, delta, sym, r, pnl in events:
        current += delta  # This needs reset
    
    # Better approach: sample at each fill
    return max_concurrent

for currency in ['CHF', 'JPY']:
    trades = df[df['symbol'].str.contains(currency)].copy()
    
    # Build timeline
    events = []
    for _, row in trades.iterrows():
        events.append((row['fill_time'], 1, row['symbol']))
        events.append((row['exit_time'], -1, row['symbol']))
    events.sort(key=lambda x: (x[0], x[1]))
    
    current = 0
    max_conc = 0
    histogram = defaultdict(int)
    last_time = None
    
    for time, delta, sym in events:
        if delta == 1 and last_time != time:
            histogram[current] += 1
        current += delta
        max_conc = max(max_conc, current)
        last_time = time
    
    # Simple count: at each fill moment, how many were already open?
    open_positions = []
    concurrent_at_fill = []
    for _, row in trades.sort_values('fill_time').iterrows():
        # Remove closed positions
        open_positions = [p for p in open_positions if p['exit_time'] > row['fill_time']]
        concurrent_at_fill.append(len(open_positions))
        open_positions.append({'symbol': row['symbol'], 'exit_time': row['exit_time']})
    
    trades_sorted = trades.sort_values('fill_time').copy()
    trades_sorted['concurrent_at_fill'] = concurrent_at_fill
    
    print(f"\n{currency} - Max concurrent: {max_conc}")
    print(f"Distribution of {currency} positions open when new {currency} trade fills:")
    for n in range(max_conc + 1):
        count = (trades_sorted['concurrent_at_fill'] == n).sum()
        print(f"  {n} already open: {count} fills ({count/len(trades)*100:.1f}%)")


# ─── STAP 3: Simulatie - welke trades zouden geblokkeerd worden? ───
print(f"\n{'='*80}")
print("SIMULATIE: Currency Exposure Limiter Impact")
print(f"{'='*80}")

def simulate_currency_limiter(df, limits):
    """
    Simulate which trades would be blocked by currency exposure limits.
    Returns (kept_trades, blocked_trades)
    """
    df_sorted = df.sort_values('fill_time').copy()
    
    kept = []
    blocked = []
    open_positions = []  # list of {symbol, exit_time, currencies}
    
    for _, row in df_sorted.iterrows():
        # Clean up closed positions
        open_positions = [p for p in open_positions if p['exit_time'] > row['fill_time']]
        
        # Count open positions per currency
        currency_count = defaultdict(int)
        for pos in open_positions:
            for curr in pos['currencies']:
                currency_count[curr] += 1
        
        # Check if this trade's currencies exceed limits
        currencies = get_currencies(row['symbol'])
        blocked_by = None
        for curr in currencies:
            limit = limits.get(curr, limits.get('default', 999))
            if currency_count[curr] >= limit:
                blocked_by = curr
                break
        
        if blocked_by:
            blocked.append({**row.to_dict(), 'blocked_by': blocked_by})
        else:
            kept.append(row.to_dict())
            open_positions.append({
                'symbol': row['symbol'],
                'exit_time': row['exit_time'],
                'currencies': currencies
            })
    
    return pd.DataFrame(kept), pd.DataFrame(blocked)

# Test multiple scenarios
scenarios = {
    "Baseline (geen limiet)": {'default': 999},
    "CHF=1, JPY=1, rest=999": {'CHF': 1, 'JPY': 1, 'default': 999},
    "CHF=1, JPY=2, rest=999": {'CHF': 1, 'JPY': 2, 'default': 999},
    "CHF=2, JPY=2, rest=999": {'CHF': 2, 'JPY': 2, 'default': 999},
    "CHF=1, JPY=1, rest=3": {'CHF': 1, 'JPY': 1, 'default': 3},
    "CHF=2, JPY=2, rest=3": {'CHF': 2, 'JPY': 2, 'default': 3},
    "Alle currencies max 2": {'default': 2},
    "Alle currencies max 3": {'default': 3},
}

print(f"\n{'Scenario':<35} {'Trades':>7} {'Blocked':>8} {'Win%':>7} {'TotalR':>9} {'AvgR':>8} {'Blocked PnL':>12} {'Blocked R':>10}")
print("─" * 105)

results = {}
for name, limits in scenarios.items():
    kept, blocked = simulate_currency_limiter(df, limits)
    
    n_kept = len(kept)
    n_blocked = len(blocked)
    wr = (kept['realized_r'] > 0).sum() / len(kept) * 100 if len(kept) > 0 else 0
    total_r = kept['realized_r'].sum()
    avg_r = kept['realized_r'].mean() if len(kept) > 0 else 0
    blocked_pnl = blocked['realized_pnl'].sum() if len(blocked) > 0 else 0
    blocked_r = blocked['realized_r'].sum() if len(blocked) > 0 else 0
    
    results[name] = {
        'kept': kept, 'blocked': blocked, 'n_kept': n_kept,
        'n_blocked': n_blocked, 'wr': wr, 'total_r': total_r,
        'blocked_pnl': blocked_pnl, 'blocked_r': blocked_r
    }
    
    print(f"{name:<35} {n_kept:>7} {n_blocked:>8} {wr:>6.1f}% {total_r:>9.2f} {avg_r:>8.4f} {blocked_pnl:>12.2f} {blocked_r:>10.2f}")

# ─── STAP 4: Detail van geblokkeerde trades voor CHF=1, JPY=1 scenario ───
print(f"\n{'='*80}")
print("DETAIL: Geblokkeerde trades bij CHF=1, JPY=1")
print(f"{'='*80}")

key = "CHF=1, JPY=1, rest=999"
blocked = results[key]['blocked']
if len(blocked) > 0:
    print(f"\nTotaal geblokkeerd: {len(blocked)} trades")
    
    # Group by blocked_by currency
    for curr in ['CHF', 'JPY']:
        curr_blocked = blocked[blocked['blocked_by'] == curr]
        if len(curr_blocked) > 0:
            wins = (curr_blocked['realized_r'] > 0).sum()
            losses = (curr_blocked['realized_r'] <= 0).sum()
            print(f"\n  Geblokkeerd door {curr} limiet: {len(curr_blocked)} trades")
            print(f"    Winners geblokkeerd: {wins} (zouden winst zijn geweest)")
            print(f"    Losers geblokkeerd: {losses} (gelukkig vermeden)")
            print(f"    Netto R geblokkeerd: {curr_blocked['realized_r'].sum():.2f}")
            print(f"    Netto PnL geblokkeerd: {curr_blocked['realized_pnl'].sum():.2f}")
            
            # Per symbol
            print(f"    Per symbol:")
            for sym in sorted(curr_blocked['symbol'].unique()):
                sub = curr_blocked[curr_blocked['symbol'] == sym]
                w = (sub['realized_r'] > 0).sum()
                l = (sub['realized_r'] <= 0).sum()
                print(f"      {sym:<15} blocked={len(sub)}, W={w}, L={l}, R={sub['realized_r'].sum():.2f}")

# ─── STAP 5: Impact op drawdown ───
print(f"\n{'='*80}")
print("ESTIMATED IMPACT OP DRAWDOWN & EQUITY CURVE")
print(f"{'='*80}")

# Simple equity curve comparison
for scenario_name in ["Baseline (geen limiet)", "CHF=1, JPY=1, rest=999", "CHF=2, JPY=2, rest=999", "Alle currencies max 2"]:
    kept = results[scenario_name]['kept']
    if len(kept) == 0:
        continue
        
    # Calculate cumulative equity (simplified - using R values)
    cumR = kept['realized_r'].cumsum()
    
    # Running max and drawdown in R-terms
    running_max = cumR.expanding().max()
    dd_r = cumR - running_max
    max_dd_r = dd_r.min()
    
    # Profit factor
    gross_wins = kept.loc[kept['realized_r'] > 0, 'realized_r'].sum()
    gross_losses = abs(kept.loc[kept['realized_r'] <= 0, 'realized_r'].sum())
    pf = gross_wins / gross_losses if gross_losses > 0 else float('inf')
    
    print(f"\n  {scenario_name}:")
    print(f"    Trades: {len(kept)}, Win%: {(kept['realized_r']>0).sum()/len(kept)*100:.1f}%")
    print(f"    Total R: {kept['realized_r'].sum():.2f}, Avg R: {kept['realized_r'].mean():.4f}")
    print(f"    Profit Factor: {pf:.2f}")
    print(f"    Max DD in R-terms: {max_dd_r:.2f}R")

# ─── STAP 6: Welke specifieke trades ZOUDEN geblokkeerd worden? Top winners & losers ───
print(f"\n{'='*80}")
print("TOP 10 GROOTSTE GEBLOKKEERDE TRADES (CHF=1, JPY=1)")
print(f"{'='*80}")

blocked = results["CHF=1, JPY=1, rest=999"]['blocked']
if len(blocked) > 0:
    blocked_sorted = blocked.sort_values('realized_pnl', ascending=False)
    
    print("\nTop 10 geblokkeerde WINNERS (gemiste winst):")
    top_winners = blocked_sorted.head(10)
    for _, t in top_winners.iterrows():
        print(f"  {t['symbol']:<15} {t['fill_time']:%Y-%m-%d} R={t['realized_r']:>+.3f} PnL={t['realized_pnl']:>+.2f} (blocked by {t['blocked_by']})")
    
    print("\nTop 10 geblokkeerde LOSERS (vermeden verlies):")
    top_losers = blocked_sorted.tail(10)
    for _, t in top_losers.iterrows():
        print(f"  {t['symbol']:<15} {t['fill_time']:%Y-%m-%d} R={t['realized_r']:>+.3f} PnL={t['realized_pnl']:>+.2f} (blocked by {t['blocked_by']})")

print(f"\n{'='*80}")
print("CONCLUSIE")
print(f"{'='*80}")

baseline = results["Baseline (geen limiet)"]
scenario1 = results["CHF=1, JPY=1, rest=999"]
scenario2 = results["CHF=2, JPY=2, rest=999"]

print(f"""
  Baseline:     {baseline['n_kept']} trades, Total R = {baseline['total_r']:.2f}
  CHF=1,JPY=1:  {scenario1['n_kept']} trades, Total R = {scenario1['total_r']:.2f} (Δ = {scenario1['total_r']-baseline['total_r']:+.2f}R)
  CHF=2,JPY=2:  {scenario2['n_kept']} trades, Total R = {scenario2['total_r']:.2f} (Δ = {scenario2['total_r']-baseline['total_r']:+.2f}R)
  
  Geblokkeerde trades CHF=1,JPY=1: {scenario1['n_blocked']} 
    → Netto R van geblokkeerde: {scenario1['blocked_r']:+.2f}R
    → Als positief: je mist winst. Als negatief: je vermijdt verlies.
""")
