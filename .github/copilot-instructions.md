# AI Assistant Instructions - 5ers Trading Bot

## Project Overview

Automated MetaTrader 5 trading bot for **5ers 20K High Stakes** Challenge accounts.

### Current State (January 20, 2026)
- **Status**: ✅ Production Ready & Validated
- **Latest Simulation**: $310,183 from $20K (+1,451%, 871 trades)
- **5ers Compliance**: Max TDD 4.94%, Max DDD 3.61% (both within limits)
- **Exit System**: 3 Take Profit levels (35%/30%/35% at 0.6R/1.2R/2.0R)
- **Entry Queue**: Signals wait for 0.3R proximity, spread protection active
- **Scan Timing**: Daily at 00:15 server time (Tue-Fri), 01:00 Monday; midnight equity sync at 00:00

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
│  • Entry queue (0.3R proximity, 120h expiry)                                │
│  • Lot sizing at FILL moment (compounding)                                  │
│  • 3-TP partial closes                                                       │
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
| `main_live_bot.py` | Live MT5 trading with entry queue & dynamic lot sizing |
| `challenge_risk_manager.py` | DDD/TDD enforcement, AccountSnapshot |
| `ftmo_config.py` | 5ers challenge configuration |
| `params/current_params.json` | Active optimized parameters |

---

## 5-TP Exit System

| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.6R | 20% | Move to breakeven |
| TP2 | 1.6R | 30% | Trail to TP1+0.5R |
| TP3 | 2.1R | 20% | Trail to TP2 |
| TP4 | 2.4R | 20% | Trail to TP3+0.5R |
| TP5 | 3.6R | 10% | Close ALL remaining |

---

## Entry Queue System

### Scan Timing
- **Daily close**: 00:00 server time
- **Midnight equity sync**: **00:00 server time** — captures MAX(equity, balance) for 5ers DDD baseline
- **Scan time (Tue-Fri)**: **00:15 server time** (15 min after daily close)
- **Scan time (Monday)**: **01:00 server time** (1 hour after market open, avoids wide spreads)

### Order Placement (3 Scenarios)

| Scenario | Condition | Action |
|----------|-----------|--------|
| A | Price ≤0.05R from entry | MARKET ORDER (spread check) |
| B | 0.05R < price ≤ 0.3R | LIMIT ORDER |
| C | Price > 0.3R | AWAITING ENTRY QUEUE |

---

## DDD Safety System (3-Tier)

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning only |
| Reduce | ≥3.0% | Reduce risk: 0.6% → 0.4% |
| Halt | ≥3.5% | Close all positions, stop trading until next day |

---

## Latest Performance (January 18, 2026)

```json
{
  "starting_balance": 20000,
  "final_balance": 310183,
  "net_return_pct": 1451,
  "total_trades": 871,
  "win_rate": 67.5,
  "max_total_dd_pct": 4.94,
  "max_daily_dd_pct": 3.61,
  "safety_events": 1,
  "total_commissions": 2924
}
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
python ftmo_challenge_analyzer.py --single --trials 100  # TPE
python ftmo_challenge_analyzer.py --multi --trials 100   # NSGA-II
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
# This enables proper compounding
lot_size = calculate_lot_size(
    balance=current_balance,  # Current, not signal-time balance
    risk_pct=0.6,
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
5. ❌ **Never run only Stage 1** - always run both validate AND simulate

---

**Last Updated**: January 20, 2026
