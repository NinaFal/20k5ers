#!/usr/bin/env python3
import re
import json

# Lees de log
with open('optimizer_live.log', 'r') as f:
    log = f.read()

# Parse trials
trials = []
lines = log.split('\n')

current_trial = None
for i, line in enumerate(lines):
    # Match trial completion
    if 'Trial' in line and 'finished with value' in line:
        match = re.search(r'Trial (\d+) finished with value: ([-\d.]+)', line)
        if match:
            trial_num = int(match.group(1))
            score = float(match.group(2))
            current_trial = {'trial': trial_num, 'score': score}
    
    # Match performance metricsif  '→ Return:' in line and current_trial:
        match = re.search(r'Return: \+([\d.]+)%, Trades: (\d+), Win: ([\d.]+)%', line)
        if match:
            current_trial['return'] = float(match.group(1))
            current_trial['trades'] = int(match.group(2))
            current_trial['winrate'] = float(match.group(3))
    
    if '→ TDD:' in line and current_trial:
        match = re.search(r'TDD: ([\d.]+)%, DDD: ([\d.]+)%, DDD Halts: (\d+)', line)
        if match:
            current_trial['tdd'] = float(match.group(1))
            current_trial['ddd'] = float(match.group(2))
            current_trial['halts'] = int(match.group(3))
            
            if 'trades' in current_trial:
                trials.append(current_trial.copy())
            current_trial = None

# Sorteer op score
trials.sort(key=lambda x: x['score'], reverse=True)

print("="*80)
print(f"Feb/Mar 2024 Optimizer Resultaten - {len(trials)} trials")
print("="*80)
print(f"\n{'Trial':<7} {'Score':<8} {'Return':<8} {'Trades':<7} {'Win%':<7} {'DDD%':<7} {'Halts':<6}")
print("-"*80)

for t in trials[:15]:
    print(f"{t['trial']:<7} {t['score']:<8.1f} {t['return']:<8.1f} {t['trades']:<7} "
          f"{t['winrate']:<7.1f} {t['ddd']:<7.2f} {t['halts']:<6}")

print("\n" + "="*80)
print(f"BESTE TRIAL: #{trials[0]['trial']}")
print("="*80)
best = trials[0]
print(f"Score: {best['score']:.2f}")
print(f"Return: +{best['return']:.1f}%")
print(f"Trades: {best['trades']}")
print(f"Win Rate: {best['winrate']:.1f}%")
print(f"Max DDD: {best['ddd']:.2f}%")
print(f"DDD Halts: {best['halts']}")

# Opslaan
with open('trials_summary.json', 'w') as f:
    json.dump({'total_trials': len(trials), 'trials': trials}, f, indent=2)

print(f"\nResultaten opgeslagen in trials_summary.json")
