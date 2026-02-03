# 5ers 20K High Stakes Trading Bot

Automated MetaTrader 5 trading bot for **5ers 20K High Stakes** Challenge accounts. Uses a **5-TP Confluence System** with multi-timeframe analysis and M15 realistic simulation.

**Last Updated**: February 3, 2026

---

## 🎯 Current Configuration

### From params/current_params.json
| Parameter | Value |
|-----------|-------|
| Risk Per Trade | 1.0% |
| Min Confluence | 3 |
| Progressive Trail | 1.0R → BE+0.4R |

### 5-TP Exit System
| Level | R-Multiple | Close % |
|-------|------------|---------|
| TP1 | 0.9R | 20% |
| TP2 | 2.9R | 20% |
| TP3 | 4.3R | 30% |
| TP4 | 4.8R | 15% |
| TP5 | 6.2R | 15% |

---

## Quick Start

```bash
# 1. Run full backtest (RECOMMENDED - tests EXACTLY what live bot does)
python backtest/src/main_live_bot_backtest.py --start 2023-01-01 --end 2025-12-31 --balance 20000

# 2. Run signal validation only (fast, generates trades CSV)
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31

# 3. Run optimization
python backtest/optimize_main_live_bot.py --trials 100 --start 2024-01-01 --end 2024-12-31

# 4. Run live bot (Windows VM with MT5)
python main_live_bot.py
```

---

## Architecture

### Backtest System

The backtest uses `main_live_bot_backtest.py` which is an **exact copy** of `main_live_bot.py` but uses CSV data instead of live MT5:

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

### Two-Environment Design
```
┌─────────────────────────────────────┐     ┌────────────────────────────────┐
│   BACKTEST (Any Platform)           │     │  LIVE BOT (Windows VM + MT5)   │
│                                      │     │                                 │
│  main_live_bot_backtest.py           │────▶│  main_live_bot.py              │
│  - Uses CSV data (M15)               │     │  - Uses real MT5               │
│  - CSVMT5Simulator                   │     │  - Real order execution        │
│                                      │     │                                 │
│  optimize_main_live_bot.py           │     │  Both use SAME:                │
│  - Optuna parameter optimization     │     │  - Entry queue system          │
│                                      │     │  - 5-TP partial close          │
│                                      │     │  - DDD/TDD safety              │
└─────────────────────────────────────┘     └────────────────────────────────┘
```

---

## Safety Systems

### DDD (Daily Drawdown) - 3 Tier
| Tier | Threshold | Action |
|------|-----------|--------|
| Warning | ≥2.0% | Log warning |
| Reduce | ≥3.0% | Reduce risk |
| Halt | ≥3.2% | Close all, stop trading |

### TDD (Total Drawdown) - STATIC
- 10% max from **starting balance** ($20K → stop-out at $18K)
- NOT trailing like FTMO

### Lot Sizing Safety
- **Metal Pip Value Fix**: XAU=$100/pip, XAG=$5/pip from fiveers_specs
- **2x Risk Rejection**: Rejects trades where actual_risk > 2x intended

---

## 5ers Challenge Rules

| Rule | Limit |
|------|-------|
| Account Size | $20,000 |
| Max Total DD | 10% (STATIC from start) |
| Max Daily DD | 5% from day start |
| Step 1 Target | 8% = $1,600 |
| Step 2 Target | 5% = $1,000 |

---

## Key Files

| File | Purpose |
|------|---------|
| `main_live_bot.py` | Live MT5 trading |
| `backtest/src/main_live_bot_backtest.py` | Backtest (exact copy of live) |
| `backtest/optimize_main_live_bot.py` | Optuna parameter optimizer |
| `strategy_core.py` | Trading signals |
| `params/current_params.json` | Active parameters |
| `tradr/brokers/fiveers_specs.py` | Contract specs |

---

## Recent Fixes (February 3, 2026)

### Critical: Metal Pip Value
MT5 tick_value was giving $1/pip for XAU instead of $100/pip, causing 59x oversizing.
**Fix**: Now uses fiveers_specs directly for XAU/XAG.

### Safety: 2x Risk Rejection
Added check to reject trades where actual_risk > 2x intended risk.

---

**Last Updated**: February 3, 2026
