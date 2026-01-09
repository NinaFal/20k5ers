# 5ers 60K High Stakes Trading Bot

Automated MetaTrader 5 trading bot for **5ers 60K High Stakes** Challenge accounts. Uses a **3-TP Confluence System** with multi-timeframe analysis. Validated with **H1 Realistic Simulation** for production-ready results.

## 🎯 Final Validated Performance (January 6, 2026)

### H1 Realistic Simulation Results
*Simulates EXACTLY what `main_live_bot.py` would do in production*

| Metric | Value |
|--------|-------|
| **Starting Balance** | $60,000 |
| **Final Balance** | **$948,629** |
| **Net Return** | **+1,481%** |
| **Total Trades** | **943** |
| **Win Rate** | **66.1%** |
| **Max Total DD** | **2.17%** (limit 10%) ✅ |
| **Max Daily DD** | **4.16%** (limit 5%) ✅ |
| **DDD Halts** | 2 (safety working) |
| **Commissions** | $9,391 |

### Entry Queue System
| Metric | Value |
|--------|-------|
| Proximity Threshold | 0.3R |
| Signals Generated | ~2,000 |
| Trades Executed | 943 (47% fill rate) |
| Max Wait Time | 5 days |

### 5ers Challenge Compliance
| Rule | Limit | Achieved | Status |
|------|-------|----------|--------|
| Max TDD | 10% | 2.17% | ✅ |
| Max DDD | 5% | 4.16% | ✅ |
| Profit Target | 8% Step 1 | +1,481% | ✅ |

---

## Quick Start

```bash
# Run full live bot simulation (RECOMMENDED)
python scripts/simulate_main_live_bot.py

# Run signal validation (TPE backtest)
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31

# Run optimization
python ftmo_challenge_analyzer.py --single --trials 100  # TPE single-objective
python ftmo_challenge_analyzer.py --multi --trials 100   # NSGA-II multi-objective

# Check optimization status
python ftmo_challenge_analyzer.py --status

# Run live bot (Windows VM with MT5)
python main_live_bot.py
```

---

## Architecture

### Two-Environment Design
```
┌─────────────────────────────────┐     ┌────────────────────────────────┐
│   OPTIMIZER (Any Platform)      │     │  LIVE BOT (Windows VM + MT5)   │
│                                  │     │                                 │
│  ftmo_challenge_analyzer.py      │────▶│  main_live_bot.py              │
│  - Optuna TPE / NSGA-II          │     │  - Loads params/current*.json  │
│  - Backtesting 2003-2025         │     │  - Entry queue system          │
│  - Parameter optimization        │     │  - 3-TP partial close          │
│                                  │     │  - Dynamic lot sizing          │
│  Output: params/current_params   │     │  - DDD/TDD safety              │
└─────────────────────────────────┘     └────────────────────────────────┘
```

### Data Flow
```
params/current_params.json       ← Optimized strategy parameters
         ↑                            ↓
ftmo_challenge_analyzer.py      main_live_bot.py
(Optuna optimization)           (loads params at startup)
         ↑                            ↓
data/ohlcv/                      scripts/simulate_main_live_bot.py
(historical D1/H1 data)          (H1 realistic simulation)
```

---

## Project Structure

```
├── strategy_core.py              # Core trading logic (3-TP system)
├── ftmo_challenge_analyzer.py    # Optimization engine & validation
├── main_live_bot.py              # Live MT5 trading entry point
├── broker_config.py              # Multi-broker configuration
├── symbol_mapping.py             # Symbol conversion (OANDA ↔ broker)
├── config.py                     # Contract specs, symbols
├── ftmo_config.py                # 5ers challenge rules
│
├── params/                       # Parameter management
│   ├── current_params.json       # Active parameters
│   ├── defaults.py               # Default parameter values
│   └── params_loader.py          # Load/save utilities
│
├── scripts/
│   └── simulate_main_live_bot.py # H1 realistic simulation (matches live bot)
│
├── data/ohlcv/                   # Historical data (D1, H1)
├── ftmo_analysis_output/         # Optimization & validation results
│   ├── FINAL_SIMULATION_JAN06_2026/  # Definitive results
│   ├── VALIDATE/                 # TPE validation results
│   └── NSGA/                     # Multi-objective results
│
└── docs/                         # Documentation
```

---

## 3-TP Exit System

The strategy uses 3 Take Profit levels with partial position closing:

| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.6R | 35% | Move to breakeven |
| TP2 | 1.2R | 30% | Trail to TP1+0.5R |
| TP3 | 2.0R | 35% | Close remaining |

**Trailing Stop**: Activated after TP1, moves to breakeven, then follows price.

---

## 5ers Challenge Rules

| Rule | Limit | Our Performance |
|------|-------|-----------------|
| Max Total Drawdown | 10% below start ($54K stop-out) | **2.17% ✅** |
| Max Daily Drawdown | 5% from day start | **4.16% ✅** |
| Step 1 Target | 8% = $4,800 | **+1,481% ✅** |
| Step 2 Target | 5% = $3,000 | **Achieved ✅** |
| Min Profitable Days | 3 | **943 trades ✅** |

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `strategy_core.py` | Trading strategy logic - 3-TP system, signals |
| `params/current_params.json` | Current optimized parameters |
| `ftmo_challenge_analyzer.py` | Optimization & validation engine |
| `scripts/simulate_main_live_bot.py` | H1 realistic simulation |
| `main_live_bot.py` | Live MT5 trading bot |
| `challenge_risk_manager.py` | DDD/TDD enforcement |

---

## Documentation

- **[docs/5ERS_COMPLIANCE.md](docs/5ERS_COMPLIANCE.md)** - 5ers rule compliance
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture
- **[docs/STRATEGY_GUIDE.md](docs/STRATEGY_GUIDE.md)** - Trading strategy details
- **[docs/EXIT_STRATEGY.md](docs/EXIT_STRATEGY.md)** - 3-TP exit system
- **[docs/CHANGELOG.md](docs/CHANGELOG.md)** - Version history
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - AI assistant guide

---

## Final Simulation Results (January 6, 2026)

### Full Live Bot Simulation (2023-2025)
```json
{
  "starting_balance": 60000,
  "final_balance": 948629,
  "net_return_pct": 1481,
  "total_trades": 943,
  "win_rate": 66.1,
  "max_total_dd_pct": 2.17,
  "max_daily_dd_pct": 4.16,
  "ddd_halt_events": 2,
  "total_commissions": 9391
}
```

**Results Location**: `ftmo_analysis_output/FINAL_SIMULATION_JAN06_2026/`

---

**Last Updated**: January 4, 2026
