
# Exit Strategy - 3-TP System

## Overview

The trading strategy uses a **3 Take Profit Level** exit system with partial position closing and dynamic trailing stops.

> **Updated January 6, 2026**: Simplified from 5-TP to 3-TP for better risk management and higher win rate.

---

## Take Profit Levels

| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.6R | 35% | Move to breakeven |
| TP2 | 1.2R | 30% | Trail to TP1+0.5R |
| TP3 | 2.0R | 35% | Close remaining |

### Parameters
```python
# R-Multiples (in params/current_params.json)
tp1_r_multiple: 0.6
tp2_r_multiple: 1.2
tp3_r_multiple: 2.0

# Close Percentages
tp1_close_pct: 0.35  # 35%
tp2_close_pct: 0.30  # 30%
tp3_close_pct: 0.35  # 35%
```

---

## Trailing Stop Logic

### Activation
Trailing stop activates after **TP1 is hit**.

### Movement Rules

| Event | Trailing SL Position |
|-------|---------------------|
| Entry | Original SL (1R away) |
| TP1 Hit | Move to entry (breakeven) |
| TP2 Hit | Move to TP1 + 0.5R |
| TP3 Hit | Close all remaining |

---

## Exit Scenarios

### Scenario A: Full TP3 Exit (Best Case)
All TPs hit in sequence:
```
Entry: 100.00, SL: 99.00 (risk = 1.00)
TP1: 100.60 → Close 35% at 0.6R → Book +0.21R
TP2: 101.20 → Close 30% at 1.2R → Book +0.36R
TP3: 102.00 → Close 35% at 2.0R → Book +0.70R

Total R = 0.35*0.6 + 0.30*1.2 + 0.35*2.0
       = 0.21 + 0.36 + 0.70
       = 1.27R
```

### Scenario B: TP1 + Trailing Exit
Price reverses after TP1:
```
Entry: 100.00, SL: 99.00, TP1: 100.60
TP1 hit → Close 35%, Trail SL to 100.00 (breakeven)
Price reverses, hits trailing at 100.00

Total R = 0.35 * 0.6 + 0.65 * 0.0 = 0.21R (still profitable!)
```

### Scenario C: TP2 + Trailing Exit
Price reverses after TP2:
```
Entry: 100.00, SL: 99.00
TP1 hit → Close 35%, Book +0.21R
TP2 hit → Close 30%, Book +0.36R, Trail to 101.10
Price hits trailing at 101.10

Trail R = (101.10 - 100.00) / 1.00 = 1.1R
Remaining = 35%

Total R = 0.21 + 0.36 + (0.35 * 1.1) = 0.21 + 0.36 + 0.385 = 0.955R
```

### Scenario D: Pure Stop Loss
No TPs hit, SL triggered:
```
Entry: 100.00, SL: 99.00
Price drops to 99.00 immediately

Total R = -1.0R
```

---

## R Calculation Formula

### Partial Profit Booking
Each TP level books profit immediately:

```python
# When TP1 hit
partial_pnl_1 = position_size * 0.35 * 0.6R

# When TP2 hit  
partial_pnl_2 = position_size * 0.30 * 1.2R

# When TP3 hit (or trailing SL)
final_pnl = position_size * 0.35 * exit_r
```

### Total PnL
```python
total_pnl = partial_pnl_1 + partial_pnl_2 + final_pnl - commissions
```

---

## Implementation Location

### scripts/simulate_main_live_bot.py
- `_check_tp_levels()` - Handles TP hits and partial closes
- `_close_position()` - Handles final close and trailing SL
- Matches exact live bot behavior

### main_live_bot.py
- Real-time MT5 execution
- Same 3-TP logic with 5-minute monitoring

---

## Key Parameters (params/current_params.json)

```json
{
    "tp1_r_multiple": 0.6,
    "tp2_r_multiple": 1.2,
    "tp3_r_multiple": 2.0,
    "tp1_close_pct": 0.35,
    "tp2_close_pct": 0.30,
    "tp3_close_pct": 0.35
}
```

---

## Validation Results

With this 3-TP system (2023-2025, H1 simulation):

| Metric | Value |
|--------|-------|
| **Total Trades** | 943 |
| **Win Rate** | 66.1% |
| **Final Balance** | $948,629 |
| **Return** | +1,481% |
| **Max TDD** | 2.17% |
| **Max DDD** | 4.16% |

---

## Why 3-TP Instead of 5-TP?

1. **Simpler execution** - Fewer partial closes to manage
2. **Higher immediate profit** - 35% at TP1 vs 10%
3. **Better breakeven protection** - More secured at first target
4. **Lower complexity** - Easier to debug and maintain
5. **Validated results** - $948K final balance proves effectiveness

---

**Last Updated**: January 6, 2026
