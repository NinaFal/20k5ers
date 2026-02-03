# Exit Strategy - 5-TP System

**Last Updated**: February 3, 2026

## Overview

The trading strategy uses a **5 Take Profit Level** exit system with partial position closing and progressive trailing stops. Parameters are loaded from `params/current_params.json`.

---

## Take Profit Levels (Current Configuration)

| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.9R | 20% | Move to breakeven |
| TP2 | 2.9R | 20% | Trail to TP1+0.5R |
| TP3 | 4.3R | 30% | Trail to TP2+0.5R |
| TP4 | 4.8R | 15% | Trail to TP3+0.5R |
| TP5 | 6.2R | 15% | Close all remaining |

### Parameters (from current_params.json)
```json
{
  "tp1_r_multiple": 0.9,
  "tp2_r_multiple": 2.9,
  "tp3_r_multiple": 4.3,
  "tp4_r_multiple": 4.8,
  "tp5_r_multiple": 6.2,
  "tp1_close_pct": 0.20,
  "tp2_close_pct": 0.20,
  "tp3_close_pct": 0.30,
  "tp4_close_pct": 0.15,
  "tp5_close_pct": 0.15
}
```

---

## Progressive Trailing Stop

### Activation
At **1.0R** profit, the stop loss moves to **breakeven + 0.4R**.

### Parameters
```json
{
  "progressive_trigger_r": 1.0,
  "progressive_trail_target_r": 0.4
}
```

---

## Exit Scenarios

### Scenario A: Full TP5 Exit (Best Case)
All TPs hit in sequence:
```
Entry: 100.00, SL: 99.00 (risk = 1.00)
TP1: 100.90 → Close 20% at 0.9R → Book +0.18R
TP2: 102.90 → Close 20% at 2.9R → Book +0.58R
TP3: 104.30 → Close 30% at 4.3R → Book +1.29R
TP4: 104.80 → Close 15% at 4.8R → Book +0.72R
TP5: 106.20 → Close 15% at 6.2R → Book +0.93R

Total R = 0.18 + 0.58 + 1.29 + 0.72 + 0.93 = 3.70R
```

### Scenario B: TP1 + Progressive Trail Exit
Price reverses after TP1:
```
Entry: 100.00, SL: 99.00, TP1: 100.90
TP1 hit → Close 20%, Book +0.18R
Price reaches 1.0R → SL moves to 100.40 (BE+0.4R)
Price reverses, hits trailing at 100.40

Trail R = (100.40 - 100.00) / 1.00 = 0.4R
Remaining = 80%

Total R = 0.18 + (0.80 * 0.4) = 0.18 + 0.32 = 0.50R
```

### Scenario C: Pure Stop Loss
No TPs hit, SL triggered:
```
Entry: 100.00, SL: 99.00
Price drops to 99.00 immediately

Total R = -1.0R
```

---

## Implementation Files

| File | Function |
|------|----------|
| `main_live_bot.py` | `_manage_tp_exits()` - Live TP management |
| `backtest/src/main_live_bot_backtest.py` | Same function for backtest |
| `params/current_params.json` | TP level configuration |

---

**Note**: The 5-TP system is optimized via `backtest/optimize_main_live_bot.py` using Optuna.
