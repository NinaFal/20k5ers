#!/usr/bin/env python3
"""
Analyzer voor de optimizer resultaten van Feb-Mar 2024
Leest de log file en genereert een overzichtsrapport
"""

import re
import json
from pathlib import Path

log_file = Path(__file__).parent / "optimizer_live.log"

# Regex patterns
trial_pattern = r"\[I.*\] Trial (\d+) finished with value: ([-\d.]+) and parameters: ({.*})"
return_pattern = r"→ Return: \+([\d.]+)%, Trades: (\d+), Win: ([\d.]+)%"
dd_pattern = r"→ TDD: ([\d.]+)%, DDD: ([\d.]+)%, DDD Halts: (\d+), Valid: (\w+)"

# Lees de log file
with open(log_file, 'r') as f:
    log_content = f.read()

# Verzamel alle trials
trials = []
trial_blocks = log_content.split('[I 2026-')

for block in trial_blocks:
    if 'Trial' not in block or 'finished with value' not in block:
        continue
    
    # Extract trial info
    trial_match = re.search(r"Trial (\d+) finished with value: ([-\d.]+) and parameters: ({.*})", block)
    if not trial_match:
        continue
    
    trial_num = int(trial_match.group(1))
    score = float(trial_match.group(2))
    params_str = trial_match.group(3)
    
    try:
        params = eval(params_str)  # Safe hier omdat we weten dat de inhoud uit de log komt
    except:
        continue
    
    # Extract performance metrics
    return_match = re.search(r"→ Return: \+([\d.]+)%, Trades: (\d+), Win: ([\d.]+)%", block)
    dd_match = re.search(r"→ TDD: ([\d.]+)%, DDD: ([\d.]+)%, DDD Halts: (\d+), Valid: (\w+)", block)
    
    if return_match and dd_match:
        trial_data = {
            'trial': trial_num,
            'score': score,
            'return_pct': float(return_match.group(1)),
            'trades': int(return_match.group(2)),
            'win_rate': float(return_match.group(3)),
            'tdd_pct': float(dd_match.group(1)),
            'ddd_pct': float(dd_match.group(2)),
            'ddd_halts': int(dd_match.group(3)),
            'valid': dd_match.group(4) == 'True',
            'parameters': params
        }
        trials.append(trial_data)

# Sorteer op score (hoogste eerst)
trials.sort(key=lambda x: x['score'], reverse=True)

print(f"\n{'='*80}")
print(f"OPTIMIZER RESULTATEN - Feb/Mar 2024")
print(f"{'='*80}")
print(f"\nTotaal voltooide trials: {len(trials)}")
print(f"Periode: 2024-02-01 tot 2024-03-31 (2 maanden)")
print(f"Startbalans: $20,000")
print(f"\n{'='*80}")
print(f"TOP 10 TRIALS (gesorteerd op score)")
print(f"{'='*80}\n")

# Header
print(f"{'Trial':<7} {'Score':<8} {'Return':<8} {'Trades':<7} {'Win%':<7} {'DDD%':<7} {'TDD%':<7} {'Halts':<6}")
print(f"{'-'*80}")

# Print top 10
for trial in trials[:10]:
    print(f"{trial['trial']:<7} {trial['score']:<8.2f} {trial['return_pct']:<8.1f} "
          f"{trial['trades']:<7} {trial['win_rate']:<7.1f} {trial['ddd_pct']:<7.2f} "
          f"{trial['tdd_pct']:<7.2f} {trial['ddd_halts']:<6}")

print(f"\n{'='*80}")
print(f"BESTE TRIAL: #{trials[0]['trial']}")
print(f"{'='*80}\n")

best = trials[0]
print(f"Score: {best['score']:.2f}")
print(f"Return: +{best['return_pct']:.1f}%")
print(f"Trades: {best['trades']}")
print(f"Win Rate: {best['win_rate']:.1f}%")
print(f"Max Daily DD: {best['ddd_pct']:.2f}%")
print(f"Max Total DD: {best['tdd_pct']:.2f}%")
print(f"DDD Halts: {best['ddd_halts']}")
print(f"\nParameters:")
print(f"  Take Profit Levels:")
print(f"    TP1: {best['parameters']['tp1_r_multiple']:.1f}R ({best['parameters']['tp1_close_pct_weight']*100:.0f}%)")
print(f"    TP2: {best['parameters']['tp2_r_multiple']:.1f}R ({best['parameters']['tp2_close_pct_weight']*100:.0f}%)")
print(f"    TP3: {best['parameters']['tp3_r_multiple']:.1f}R ({best['parameters']['tp3_close_pct_weight']*100:.0f}%)")
print(f"    TP4: {best['parameters']['tp4_r_multiple']:.1f}R ({best['parameters']['tp4_close_pct_weight']*100:.0f}%)")
print(f"    TP5: {best['parameters']['tp5_r_multiple']:.1f}R ({best['parameters']['tp5_close_pct_weight']*100:.0f}%)")
print(f"  Trailing:")
print(f"    Activation: {best['parameters']['trail_activation_r']:.1f}R")
print(f"    ATR Multiplier: {best['parameters']['atr_trail_multiplier']:.1f}x")
print(f"    Use ATR Trailing: {best['parameters']['use_atr_trailing']}")
print(f"  Entry Filters:")
print(f"    Trend Min Confluence: {best['parameters']['trend_min_confluence']}")
print(f"    Range Min Confluence: {best['parameters']['range_min_confluence']}")
print(f"    Min Quality Factors: {best['parameters']['min_quality_factors']}")
print(f"  Risk:")
print(f"    Risk per Trade: {best['parameters']['risk_per_trade_pct']:.2f}%")
print(f"    Compound Threshold: {best['parameters']['compound_threshold_pct']:.1f}%")

# Sla complete resultaten op als JSON
output_file = Path(__file__).parent / "trials_summary.json"
with open(output_file, 'w') as f:
    json.dump({
        'total_trials': len(trials),
        'period': '2024-02-01 to 2024-03-31',
        'starting_balance': 20000,
        'trials': trials
    }, f, indent=2)

print(f"\n{'='*80}")
print(f"Volledige resultaten opgeslagen in: trials_summary.json")
print(f"{'='*80}\n")

# Statistieken
print(f"\n{'='*80}")
print(f"STATISTIEKEN")
print(f"{'='*80}\n")

valid_trials = [t for t in trials if t['valid'] and t['trades'] > 0]
print(f"Trials met trades: {len(valid_trials)}/{len(trials)}")

if valid_trials:
    avg_return = sum(t['return_pct'] for t in valid_trials) / len(valid_trials)
    avg_trades = sum(t['trades'] for t in valid_trials) / len(valid_trials)
    avg_winrate = sum(t['win_rate'] for t in valid_trials) / len(valid_trials)
    max_ddd = max(t['ddd_pct'] for t in valid_trials)
    
    print(f"Gemiddeld Return: {avg_return:.1f}%")
    print(f"Gemiddeld Trades: {avg_trades:.0f}")
    print(f"Gemiddeld Win Rate: {avg_winrate:.1f}%")
    print(f"Max DDD over alle trials: {max_ddd:.2f}%")
    
    # DDD halts analyse
    trials_with_halts = [t for t in valid_trials if t['ddd_halts'] > 0]
    print(f"\nTrials met DDD Halts: {len(trials_with_halts)}/{len(valid_trials)}")
    
    # Return distributie
    high_return = [t for t in valid_trials if t['return_pct'] >= 20]
    medium_return = [t for t in valid_trials if 15 <= t['return_pct'] < 20]
    low_return = [t for t in valid_trials if t['return_pct'] < 15]
    
    print(f"\nReturn distributie:")
    print(f"  ≥20%: {len(high_return)} trials")
    print(f"  15-20%: {len(medium_return)} trials")
    print(f"  <15%: {len(low_return)} trials")
