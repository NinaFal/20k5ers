import re
import json

with open('optimizer_live.log') as f:
    log = f.read()

trials = []
for block in log.split('[I 2026-'):
    if 'Trial' not in block or 'finished with value' not in block:
        continue
    
    # Extract data
    t_match = re.search(r'Trial (\d+) finished with value: ([-\d.]+)', block)
    r_match = re.search(r'Return: \+([\d.]+)%, Trades: (\d+), Win: ([\d.]+)%', block)
    d_match = re.search(r'TDD: ([\d.]+)%, DDD: ([\d.]+)%, DDD Halts: (\d+)', block)
    
    if t_match and r_match and d_match:
        trials.append({
            'trial': int(t_match.group(1)),
            'score': float(t_match.group(2)),
            'return': float(r_match.group(1)),
            'trades': int(r_match.group(2)),
            'winrate': float(r_match.group(3)),
            'tdd': float(d_match.group(1)),
            'ddd': float(d_match.group(2)),
            'halts': int(d_match.group(3))
        })

trials.sort(key=lambda x: x['score'], reverse=True)

print("="*80)
print(f"OPTIMIZER RESULTATEN - {len(trials)} trials voltooid")
print("="*80)
print(f"\n{'Trial':<7} {'Score':<8} {'Return':<8} {'Trades':<7} {'Win%':<7} {'DDD%':<7} {'Halts':<6}")
print("-"*80)

for t in trials[:15]:
    print(f"{t['trial']:<7} {t['score']:<8.1f} {t['return']:<8.1f} {t['trades']:<7} {t['winrate']:<7.1f} {t['ddd']:<7.2f} {t['halts']:<6}")

print("\n" + "="*80)
print(f"BESTE TRIAL: #{trials[0]['trial']}")
print("="*80)
best = trials[0]
print(f"\nScore: {best['score']:.2f}")
print(f"Return: +{best['return']:.1f}%")
print(f"Trades: {best['trades']}")
print(f"Win Rate: {best['winrate']:.1f}%")
print(f"Max DDD: {best['ddd']:.2f}%")
print(f"DDD Halts: {best['halts']}")

with open('trials_summary.json', 'w') as f:
    json.dump({'total_trials': len(trials), 'trials': trials}, f, indent=2)

print(f"\n✅ Resultaten opgeslagen in trials_summary.json")

# Stats
valid = [t for t in trials if t['trades'] > 0]
print(f"\n{'='*80}")
print(f"STATISTIEKEN ({len(valid)} trials met trades)")
print("="*80)
avg_ret = sum(t['return'] for t in valid) / len(valid)
avg_win = sum(t['winrate'] for t in valid) / len(valid)
print(f"Gemiddeld return: {avg_ret:.1f}%")
print(f"Gemiddeld winrate: {avg_win:.1f}%")
print(f"Return ≥20%: {len([t for t in valid if t['return'] >= 20])} trials")
print(f"Trials met halts: {len([t for t in valid if t['halts'] > 0])}")
