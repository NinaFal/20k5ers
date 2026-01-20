# Trading Strategy Guide

## Overview

The trading strategy uses **multi-timeframe confluence analysis** with a **3-TP exit system**.

---

## Signal Generation

### Confluence System
Signals are generated via `compute_confluence()` in `strategy_core.py`.

**Confluence factors:**
- HTF Bias (Weekly/Monthly)
- Market Structure (D1)
- Fib Retracement (0.618-0.786)
- Liquidity zones
- Location (S/R levels)

### Minimum Requirements
```python
min_confluence = 2      # From params
min_quality_factors = 3 # From FIVEERS_CONFIG
```

---

## Entry Queue System

Signals don't execute immediately - they wait for price proximity:

| Condition | Action |
|-----------|--------|
| Price ≤0.05R from entry | Market order (spread check) |
| Price ≤0.3R from entry | Limit order |
| Price >0.3R from entry | Wait in queue (max 5 days) |

**Result**: ~50% fill rate with better entries

---

## 3-TP Exit System

| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.6R | 35% | Move to breakeven |
| TP2 | 1.2R | 30% | Trail to TP1+0.5R |
| TP3 | 2.0R | 35% | Close remaining |

### Expected R per Trade
```
Full TP3 hit: 0.35*0.6 + 0.30*1.2 + 0.35*2.0 = 1.27R
TP1 + reversal: 0.35*0.6 + 0.65*0.0 = 0.21R
Full SL: -1.0R
```

---

## Lot Sizing

**CRITICAL**: Lot size is calculated at FILL moment (not signal time).

```python
# This enables proper compounding
lot_size = calculate_lot_size(
    balance=current_balance,  # Balance when order fills
    risk_pct=0.6,
    entry=fill_price,
    stop_loss=sl,
)
```

---

## DDD Safety (3-Tier)

| Daily DD | Action |
|----------|--------|
| ≥2.0% | Warning logged |
| ≥3.0% | Risk reduced: 0.6% → 0.4% |
| ≥3.5% | Trading halted until next day |

---

## Key Parameters

From `params/current_params.json`:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| min_confluence | 2 | Minimum signal score |
| min_quality_factors | 3 | Quality gate |
| risk_per_trade_pct | 0.6 | Base risk per trade |
| tp1_r_multiple | 0.6 | First take profit |
| tp2_r_multiple | 1.2 | Second take profit |
| tp3_r_multiple | 2.0 | Final take profit |
| tp1_close_pct | 0.35 | % at TP1 |
| tp2_close_pct | 0.30 | % at TP2 |
| tp3_close_pct | 0.35 | % at TP3 |

---

## Performance

### Backtest Results (2023-2025)
```
Starting: $20,000
Final:    $310,183
Return:   +1,451%
Trades:   871
Win Rate: 67.5%
Max TDD:  4.94%
Max DDD:  3.61%
```

---

**Last Updated**: January 20, 2026
