# AI Assistant Instructions - 5ers Trading Bot

## Project Overview

Automated MetaTrader 5 trading bot for **5ers 20K High Stakes** Challenge accounts.

### Current State (February 3, 2026)
- **Status**: ✅ Production Ready & Validated
- **Risk Per Trade**: 1.0% (from current_params.json)
- **Exit System**: 5 Take Profit levels (configurable via params)
- **Entry Queue**: Signals wait for 0.3R proximity, spread protection active
- **Scan Timing**: Daily at 01:00 server time (1 hour after close)

### Critical Fixes Applied (Feb 3, 2026)
- **Metal Pip Value Fix**: XAU uses $100/pip, XAG uses $5/pip from fiveers_specs (not MT5 tick_value)
- **2x Risk Rejection**: Trades where actual_risk > 2x intended are rejected

---

## Backtest Architecture

**CRITICAL**: The backtest uses `main_live_bot_backtest.py` which is an **exact copy** of `main_live_bot.py`:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACKTEST = main_live_bot_backtest.py                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  backtest/src/main_live_bot_backtest.py                                     │
│  ═══════════════════════════════════════                                     │
│  • Uses CSVMT5Simulator instead of real MT5                                 │
│  • M15 tick-by-tick simulation                                              │
│  • Entry queue (0.3R proximity, 168h expiry)                                │
│  • Lot sizing at FILL moment (compounding)                                  │
│  • 5-TP partial closes                                                       │
│  • DDD/TDD safety checks                                                     │
│  • Correlation filter                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Modules

| File | Purpose |
|------|---------|
| `strategy_core.py` | Trading strategy - `compute_confluence()`, `simulate_trades()` |
| `ftmo_challenge_analyzer.py` | Optimization & `--validate` for signal generation |
| `backtest/src/main_live_bot_backtest.py` | Backtest version matching `main_live_bot.py` EXACTLY |
| `backtest/optimize_main_live_bot.py` | Optuna optimizer for finding best parameters |
| `main_live_bot.py` | Live MT5 trading with entry queue & dynamic lot sizing |
| `challenge_risk_manager.py` | DDD/TDD enforcement, AccountSnapshot |
| `ftmo_config.py` | 5ers challenge configuration |
| `params/current_params.json` | Active optimized parameters |
| `tradr/brokers/fiveers_specs.py` | Contract specs (pip_value, pip_size, min_lot) |

---

## 5-TP Exit System (from current_params.json)

| Level | R-Multiple | Close % |
|-------|------------|---------|
| TP1 | 0.9R | 20% |
| TP2 | 2.9R | 20% |
| TP3 | 4.3R | 30% |
| TP4 | 4.8R | 15% |
| TP5 | 6.2R | 15% |

**Progressive Trailing**: At 1.0R profit, SL moves to BE + 0.4R

---

## Entry Queue System

### Scan Timing
- **Daily close**: 00:00 server time
- **Scan time**: **01:00 server time** (1 hour after daily close)

### Order Placement (3 Scenarios)

| Scenario | Condition | Action |
|----------|-----------|--------|
| A | Price ≤0.05R from entry | MARKET ORDER (spread check) |
| B | 0.05R < price ≤ 1.5R | LIMIT ORDER |
| C | Price > 1.5R | AWAITING ENTRY QUEUE (168h expiry) |

---

## DDD Safety System (3-Tier)

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning only |
| Reduce | ≥3.0% | Reduce risk |
| Halt | ≥3.2% | Close all positions, stop trading until next day |

---

## Lot Sizing Safety

### Metal Pip Value (CRITICAL)
```python
# XAU and XAG use fiveers_specs directly (not MT5 tick_value!)
# MT5 tick_value was returning $1/pip instead of $100/pip for XAU
if any(x in symbol for x in ["XAU", "XAG"]):
    pip_value = fiveers_specs["pip_value_per_lot"]  # XAU=$100, XAG=$5
```

### 2x Risk Rejection
```python
# Reject trades where actual risk exceeds 2x intended
if actual_risk_pct > risk_pct * 2:
    return 0.0  # NO TRADE
```

---

## Commands

### Full Backtest (RECOMMENDED)
```bash
python backtest/src/main_live_bot_backtest.py --start 2023-01-01 --end 2025-12-31 --balance 20000
```

### Quick Signal Validation
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
```

### Optimization
```bash
python backtest/optimize_main_live_bot.py --trials 100 --start 2024-01-01 --end 2024-12-31
```

---

## Critical Conventions

### Symbol Format
- **Internal/Data**: OANDA format with underscores (`EUR_USD`, `XAU_USD`)
- **MT5 Execution**: Broker format (`EURUSD`, `XAUUSD`)

### Parameters - NEVER Hardcode
```python
# ✅ CORRECT
from params.params_loader import load_strategy_params
params = load_strategy_params()

# ❌ WRONG
MIN_CONFLUENCE = 5  # Don't hardcode
```

### Lot Sizing - At FILL Moment
```python
# Lot size calculated when order FILLS, not when signal generated
lot_size = calculate_lot_size(
    balance=current_balance,  # Current, not signal-time balance
    risk_pct=1.0,
    entry=fill_price,
    stop_loss=sl,
)
```

---

## 5ers Challenge Rules

| Rule | Limit |
|------|-------|
| Account Size | $20,000 |
| Max Total DD | 10% below start ($18K stop-out) - STATIC |
| Max Daily DD | 5% from day start ($1K max daily loss) |
| Step 1 Target | 8% = $1,600 |
| Step 2 Target | 5% = $1,000 |

**Key**: TDD is STATIC from initial balance, NOT trailing.

---

## What NOT to Do

1. ❌ **Never hardcode parameters** - use params_loader
2. ❌ **Never change exit logic** without full simulation
3. ❌ **Never use trailing TDD** - 5ers uses STATIC TDD
4. ❌ **Never calculate lot size at signal time** - use fill time balance
5. ❌ **Never trust MT5 tick_value for metals** - use fiveers_specs

---

**Last Updated**: February 3, 2026
