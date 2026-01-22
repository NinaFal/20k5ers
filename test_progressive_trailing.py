#!/usr/bin/env python3
"""
Test progressive trailing stop vs current strategy.

Current strategy:
- TP1 (0.6R): SL → Breakeven (0R)
- TP2 (1.2R): SL → TP1+0.5R (1.1R)

Progressive strategy (Option A):
- TP1 (0.6R): SL → Breakeven (0R)
- At 0.9R (75% to TP2): SL → TP1 (0.6R)
- TP2 (1.2R): SL → TP1+0.5R (1.1R)

We'll simulate hypothetical scenarios to see impact.
"""

def current_strategy_outcome(max_r_reached: float) -> float:
    """Returns R-multiple profit with current strategy."""
    # TP levels
    tp1_r = 0.6
    tp2_r = 1.2
    tp3_r = 2.0
    
    # Close percentages
    tp1_pct = 0.35
    tp2_pct = 0.30
    tp3_pct = 0.35  # remaining
    
    # Current strategy SL
    sl_after_tp1 = 0.0  # breakeven
    sl_after_tp2 = 1.1  # TP1 + 0.5R
    
    # Calculate outcome
    profit = 0
    
    if max_r_reached >= tp1_r:
        # TP1 hit - close 35%
        profit += tp1_r * tp1_pct
        remaining_pct = 1.0 - tp1_pct
        
        if max_r_reached >= tp2_r:
            # TP2 hit - close 30%
            profit += tp2_r * tp2_pct
            remaining_pct -= tp2_pct
            
            if max_r_reached >= tp3_r:
                # TP3 hit - close remaining
                profit += tp3_r * remaining_pct
            else:
                # Stopped between TP2-TP3 at SL (1.1R)
                profit += sl_after_tp2 * remaining_pct
        else:
            # Stopped between TP1-TP2 at SL (0R - breakeven!)
            profit += sl_after_tp1 * remaining_pct  # 0!
    else:
        # TP1 not reached - full stop loss
        profit = -1.0
    
    return profit


def progressive_strategy_outcome(max_r_reached: float) -> float:
    """Returns R-multiple profit with progressive trailing."""
    tp1_r = 0.6
    tp2_r = 1.2
    tp3_r = 2.0
    
    tp1_pct = 0.35
    tp2_pct = 0.30
    tp3_pct = 0.35
    
    # Progressive SL
    sl_after_tp1 = 0.0  # breakeven initially
    progressive_trigger = 0.9  # At 0.9R, move SL to TP1
    sl_progressive = 0.6  # Move to TP1
    sl_after_tp2 = 1.1
    
    profit = 0
    
    if max_r_reached >= tp1_r:
        profit += tp1_r * tp1_pct
        remaining_pct = 1.0 - tp1_pct
        
        if max_r_reached >= tp2_r:
            profit += tp2_r * tp2_pct
            remaining_pct -= tp2_pct
            
            if max_r_reached >= tp3_r:
                profit += tp3_r * remaining_pct
            else:
                profit += sl_after_tp2 * remaining_pct
        else:
            # Between TP1 and TP2
            if max_r_reached >= progressive_trigger:
                # Progressive SL (0.6R)
                profit += sl_progressive * remaining_pct
            else:
                # Breakeven
                profit += sl_after_tp1 * remaining_pct
    else:
        profit = -1.0
    
    return profit


# Test scenarios
print("="*70)
print("PROGRESSIVE TRAILING STOP TEST")
print("="*70)
print()
print("Comparing current vs progressive strategy:")
print("  Current: TP1 → BE, TP2 → 1.1R")
print("  Progressive: TP1 → BE, 0.9R → 0.6R, TP2 → 1.1R")
print()
print("="*70)
print(f"{'Scenario':<30} {'Current':<15} {'Progressive':<15} {'Delta':<10}")
print("="*70)

scenarios = [
    ("Full win to TP3", 2.5),
    ("Stopped at TP2", 1.2),
    ("Just below TP2 (1.15R)", 1.15),
    ("Just above trigger (0.95R)", 0.95),
    ("Just below trigger (0.85R)", 0.85),
    ("Just above TP1 (0.7R)", 0.7),
    ("Exactly at TP1", 0.6),
    ("Stop loss hit", 0.3),
]

total_current = 0
total_progressive = 0

for desc, max_r in scenarios:
    current = current_strategy_outcome(max_r)
    progressive = progressive_strategy_outcome(max_r)
    delta = progressive - current
    
    total_current += current
    total_progressive += progressive
    
    delta_str = f"+{delta:.2f}R" if delta > 0 else f"{delta:.2f}R"
    print(f"{desc:<30} {current:>6.2f}R       {progressive:>6.2f}R       {delta_str:>8}")

print("="*70)
print(f"{'TOTAL':<30} {total_current:>6.2f}R       {total_progressive:>6.2f}R       {total_progressive-total_current:>+8.2f}R")
print("="*70)
print()
print("KEY INSIGHT:")
print(f"  Scenarios where progressive helps:")
scenarios_helped = [
    (desc, max_r) for desc, max_r in scenarios 
    if progressive_strategy_outcome(max_r) > current_strategy_outcome(max_r)
]
for desc, max_r in scenarios_helped:
    delta = progressive_strategy_outcome(max_r) - current_strategy_outcome(max_r)
    print(f"    - {desc} (max: {max_r}R): +{delta:.2f}R")
print()
print("RECOMMENDATION:")
if total_progressive > total_current:
    print(f"  ✅ Progressive trailing shows +{total_progressive-total_current:.2f}R improvement")
    print("  → Consider implementing after full backtest validation")
else:
    print(f"  ⚠️ Progressive trailing shows {total_progressive-total_current:.2f}R difference")
    print("  → Marginal benefit, would need full backtest to confirm")
