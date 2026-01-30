# 5ers 20K High Stakes Trading Bot

Automated MetaTrader 5 trading bot for **5ers 20K High Stakes** Challenge accounts. Uses a **3-TP Confluence System** with multi-timeframe analysis and H1 realistic simulation.

## 🎯 Latest Validated Performance (January 18, 2026)

### H1 Realistic Simulation (2023-2025)
*Simulates EXACTLY what `main_live_bot.py` does in production*

| Metric | Value |
|--------|-------|
| **Starting Balance** | $20,000 |
| **Final Balance** | **$310,183** |
| **Net Return** | **+1,451%** |
| **Total Trades** | **871** |
| **Win Rate** | **67.5%** |
| **Max Total DD** | **4.94%** (limit 10%) ✅ |
| **Max Daily DD** | **3.61%** (limit 5%) ✅ |
| **Safety Events** | 1 (DDD halt working) |
| **Commissions** | $2,924 |

### 5ers Challenge Compliance
| Rule | Limit | Achieved | Status |
|------|-------|----------|--------|
| Max TDD | 10% | 4.94% | ✅ |
| Max DDD | 5% | 3.61% | ✅ |
| Profit Target | 8% Step 1 | +1,451% | ✅ |

---

## Quick Start

```bash
# 1. Run full backtest (RECOMMENDED - tests EXACTLY what live bot does)
python backtest/src/main_live_bot_backtest.py --start 2023-01-01 --end 2025-12-31 --balance 20000

# 2. Run signal validation only (fast, generates trades CSV)
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31

# 3. Run optimization
python ftmo_challenge_analyzer.py --single --trials 100  # TPE single-objective
python ftmo_challenge_analyzer.py --multi --trials 100   # NSGA-II multi-objective

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
│  • Entry queue (0.3R proximity, 120h expiry)                                │
│  • Lot sizing at FILL moment (compounding)                                  │
│  • 3-TP partial closes                                                       │
│  • DDD/TDD safety checks                                                     │
│  • Correlation filter                                                        │
│  • Purpose: Realistic P&L matching EXACTLY what live bot does               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Two-Environment Design
```
┌─────────────────────────────────┐     ┌────────────────────────────────┐
│   BACKTEST (Any Platform)       │     │  LIVE BOT (Windows VM + MT5)   │
│                                  │     │                                 │
│  main_live_bot_backtest.py       │────▶│  main_live_bot.py              │
│  - Uses CSV data (M15)           │     │  - Uses real MT5               │
│  - CSVMT5Simulator               │     │  - Real order execution        │
│                                  │     │                                 │
│  ftmo_challenge_analyzer.py      │     │  Both use SAME:                │
│  - Parameter optimization        │     │  - Entry queue system          │
│  - Quick signal validation       │     │  - 3-TP partial close          │
│                                  │     │  - DDD/TDD safety              │
└─────────────────────────────────┘     └────────────────────────────────┘
```

---

## 3-TP Exit System

| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.6R | 35% | Move to breakeven |
| TP2 | 1.2R | 30% | Trail to TP1+0.5R |
| TP3 | 2.0R | 35% | Close remaining |

---

## Entry Queue System

| Parameter | Value |
|-----------|-------|
| Proximity Threshold | 0.3R |
| Immediate Entry | ≤0.05R |
| Max Wait Time | 120 hours (5 days) |
| Fill Rate | ~50% of signals |

**Scenarios:**
- **Price ≤0.05R** → Market order (spread check active)
- **Price ≤0.3R** → Limit order
- **Price >0.3R** → Wait in queue

---

## DDD Safety System (3-Tier)

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning |
| Reduce | ≥3.0% | Reduce risk: 0.6% → 0.4% |
| Halt | ≥3.5% | Close all, stop until next day |

---

## 5ers Challenge Rules

| Rule | Limit | Our Performance |
|------|-------|-----------------|
| Max Total DD | 10% below start | **4.94% ✅** |
| Max Daily DD | 5% from day start | **3.61% ✅** |
| Step 1 Target | 8% = $1,600 | **+1,451% ✅** |

**Key**: TDD is STATIC from initial balance ($20K), NOT trailing.

---

## Project Structure

```
├── strategy_core.py              # Trading strategy (3-TP, compute_confluence)
├── ftmo_challenge_analyzer.py    # Optimization & signal validation
├── main_live_bot.py              # Live MT5 trading
├── challenge_risk_manager.py     # DDD/TDD enforcement
├── ftmo_config.py                # 5ers challenge rules
│
├── backtest/src/
│   └── main_live_bot_backtest.py # Backtest version (MATCHES LIVE BOT EXACTLY)
│
├── params/
│   ├── current_params.json       # Active parameters
│   └── params_loader.py          # Load utilities
│
├── data/ohlcv/                   # Historical data (D1, H1)
└── ftmo_analysis_output/         # Results
    └── SIMULATE_2023_2025_20K_JAN18/  # Latest simulation
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `strategy_core.py` | Trading strategy - `compute_confluence()`, `simulate_trades()` |
| `ftmo_challenge_analyzer.py` | Optimization & `--validate` for signal generation |
| `backtest/src/main_live_bot_backtest.py` | Backtest matching `main_live_bot.py` EXACTLY |
| `main_live_bot.py` | Live MT5 trading |
| `params/current_params.json` | Optimized parameters |
| `challenge_risk_manager.py` | DDD/TDD safety |

---

## Documentation

- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - AI Assistant instructions
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture
- **[docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md)** - Trading strategy
- **[docs/EXIT_STRATEGY.md](docs/EXIT_STRATEGY.md)** - 3-TP exit system

---

**Last Updated**: January 20, 2026
