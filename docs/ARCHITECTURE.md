# System Architecture

## Overview

The trading bot uses a **Two-Level Backtest Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACKTEST = VALIDATE + SIMULATE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STAGE 1: ftmo_challenge_analyzer.py --validate                             │
│  ════════════════════════════════════════════════                            │
│  • Generates D1 signals using compute_confluence()                          │
│  • Outputs: trades CSV with entry/SL/TP levels                              │
│  • Purpose: Signal generation & filtering                                    │
│                                                                              │
│                              ↓ trades CSV                                    │
│                                                                              │
│  STAGE 2: scripts/main_live_bot_backtest.py                                 │
│  ══════════════════════════════════════════════                              │
│  • Simulates H1 execution of trades                                         │
│  • Entry queue (0.3R proximity, 120h expiry)                                │
│  • Lot sizing at FILL moment (compounding)                                  │
│  • 3-TP partial closes                                                       │
│  • DDD/TDD safety checks                                                     │
│  • Purpose: Realistic P&L with proper money management                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Two-Environment Design
```
┌─────────────────────────────────┐     ┌────────────────────────────────┐
│   OPTIMIZER (Any Platform)      │     │  LIVE BOT (Windows VM + MT5)   │
│                                  │     │                                 │
│  ftmo_challenge_analyzer.py      │────▶│  main_live_bot.py              │
│  - Optuna TPE / NSGA-II          │     │  - Loads params/current*.json  │
│  - Signal generation             │     │  - Entry queue system          │
│                                  │     │  - 3-TP partial close          │
│  main_live_bot_backtest.py       │     │  - Dynamic lot sizing          │
│  - H1 realistic simulation       │     │  - DDD/TDD safety              │
└─────────────────────────────────┘     └────────────────────────────────┘
```

---

## Core Modules

### Trading Logic
| Module | Purpose |
|--------|---------|
| `strategy_core.py` | `compute_confluence()`, `simulate_trades()`, signals |
| `indicators.py` | Technical indicators (RSI, ATR, EMAs, etc.) |

### Optimization & Validation
| Module | Purpose |
|--------|---------|
| `ftmo_challenge_analyzer.py` | `--validate` for signal generation |
| `scripts/main_live_bot_backtest.py` | H1 simulation matching live bot |

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

---

## Data Flow

### Backtest Flow
```
1. ftmo_challenge_analyzer.py --validate
   └── Load D1 data from data/ohlcv/
   └── Generate signals via compute_confluence()
   └── Output: trades CSV

2. main_live_bot_backtest.py
   └── Load trades CSV + H1 data
   └── Entry queue simulation (0.3R proximity)
   └── Lot sizing at FILL moment
   └── 3-TP exit management
   └── DDD/TDD checks
   └── Output: simulation_results.json
```

### Live Trading Flow
```
1. Load params/current_params.json
2. Connect to MT5 via broker_config.py
3. Daily scan at 00:10 server time
4. Entry queue management (0.3R, 120h)
5. Lot sizing at fill moment
6. 3-TP exit system
7. DDD/TDD protection loop (every 5 sec)
```

---

## Key Classes

### StrategyParams (strategy_core.py)
```python
@dataclass
class StrategyParams:
    min_confluence: int = 2
    min_quality_factors: int = 3
    risk_per_trade_pct: float = 0.6
    tp1_r_multiple: float = 0.6
    tp2_r_multiple: float = 1.2
    tp3_r_multiple: float = 2.0
    tp1_close_pct: float = 0.35
    tp2_close_pct: float = 0.30
    tp3_close_pct: float = 0.35
```

### SimConfig (main_live_bot_backtest.py)
```python
@dataclass
class SimConfig:
    initial_balance: float = 20000
    risk_per_trade_pct: float = 0.6
    limit_order_proximity_r: float = 0.3
    max_entry_wait_hours: float = 120
    daily_loss_halt_pct: float = 3.5
    max_total_dd_pct: float = 10.0
```

---

**Last Updated**: January 20, 2026
