# System Architecture

**Last Updated**: February 3, 2026

## Overview

The trading bot uses a **Single-Source Architecture** where the backtest uses an exact copy of the live bot code.

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
│  backtest/optimize_main_live_bot.py                                         │
│  ════════════════════════════════════                                        │
│  • Optuna TPE / NSGA-II optimizer                                           │
│  • Runs main_live_bot_backtest.py with different params                     │
│  • Saves best params to params/current_params.json                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Two-Environment Design
```
┌─────────────────────────────────────┐     ┌────────────────────────────────┐
│   BACKTEST/OPTIMIZE (Any Platform)  │     │  LIVE BOT (Windows VM + MT5)   │
│                                      │     │                                 │
│  main_live_bot_backtest.py           │────▶│  main_live_bot.py              │
│  optimize_main_live_bot.py           │     │  - Loads params/current*.json  │
│  - Signal generation                 │     │  - Entry queue system          │
│  - M15 tick simulation               │     │  - 5-TP partial close          │
│  - Parameter optimization            │     │  - Dynamic lot sizing          │
│                                      │     │  - DDD/TDD safety              │
└─────────────────────────────────────┘     └────────────────────────────────┘
```

---

## Core Modules

### Trading Logic
| Module | Purpose |
|--------|---------|
| `strategy_core.py` | `compute_confluence()`, `simulate_trades()`, signals |
| `indicators.py` | Technical indicators (RSI, ATR, EMAs, etc.) |

### Backtest & Optimization
| Module | Purpose |
|--------|---------|
| `backtest/src/main_live_bot_backtest.py` | Backtest (exact copy of live) |
| `backtest/optimize_main_live_bot.py` | Optuna parameter optimization |
| `backtest/src/csv_mt5_simulator.py` | CSV-based MT5 simulator |

### Live Trading
| Module | Purpose |
|--------|---------|
| `main_live_bot.py` | Live MT5 trading execution |
| `challenge_risk_manager.py` | DDD/TDD enforcement |
| `ftmo_config.py` | 5ers challenge configuration |

### Configuration
| Module | Purpose |
|--------|---------|
| `params/current_params.json` | Active optimized parameters |
| `params/params_loader.py` | Parameter loading utilities |
| `tradr/brokers/fiveers_specs.py` | Contract specifications |

---

## Data Flow

### Optimization Flow
```
1. optimize_main_live_bot.py
   └── Define parameter search space
   └── For each trial:
       └── Generate params
       └── Run main_live_bot_backtest.py
       └── Collect metrics (return, DD, win rate)
   └── Save best to params/current_params.json
```

### Backtest Flow
```
1. main_live_bot_backtest.py
   └── Load params/current_params.json
   └── Load M15 data from data/ohlcv/
   └── Generate signals via compute_confluence()
   └── Entry queue simulation (0.3R proximity)
   └── Lot sizing at FILL moment
   └── 5-TP exit management
   └── DDD/TDD checks
   └── Output: results JSON, trades CSV
```

### Live Trading Flow
```
1. main_live_bot.py
   └── Load params/current_params.json
   └── Connect to MT5 via broker_config.py
   └── Daily scan at 01:00 server time
   └── Entry queue management (0.3R, 168h)
   └── 5-TP management
   └── DDD/TDD protection loop
```

---

## Safety Systems

### Metal Pip Value (CRITICAL FIX - Feb 3, 2026)
```python
# XAU/XAG use fiveers_specs, not MT5 tick_value
if any(x in symbol for x in ["XAU", "XAG"]):
    pip_value = fiveers_specs["pip_value_per_lot"]
```

### 2x Risk Rejection
```python
# Reject if actual risk > 2x intended
if actual_risk_pct > risk_pct * 2:
    return 0.0  # NO TRADE
```

---

**Last Updated**: February 3, 2026
