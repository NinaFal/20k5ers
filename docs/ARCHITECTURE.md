# System Architecture

## Overview

```
┌─────────────────────────────────┐     ┌────────────────────────────────┐
│   OPTIMIZER (Any Platform)      │     │  LIVE BOT (Windows VM + MT5)   │
│                                  │     │                                 │
│  ftmo_challenge_analyzer.py      │────▶│  main_live_bot.py              │
│  - Optuna TPE / NSGA-II          │     │  - Loads params/current*.json  │
│  - Backtesting 2003-2025         │     │  - Real-time MT5 execution     │
│  - H1 realistic validation       │     │  - 5 Take Profit levels        │
└─────────────────────────────────┘     └────────────────────────────────┘
```

---

## Core Modules

### Trading Logic

| Module | Purpose |
|--------|---------|
| `strategy_core.py` | Core trading strategy - signals, confluence, 5-TP exit system |
| `indicators.py` | Technical indicators (RSI, ATR, EMAs, Bollinger, etc.) |
| `trade_state.py` | Trade state management and persistence |

### Optimization & Validation

| Module | Purpose |
|--------|---------|
| `ftmo_challenge_analyzer.py` | Optuna optimization engine (TPE/NSGA-II) |
| `scripts/validate_h1_realistic.py` | H1 realistic simulation validator |
| `tradr/backtest/h1_trade_simulator.py` | Hour-by-hour trade simulation |

### Live Trading

| Module | Purpose |
|--------|---------|
| `main_live_bot.py` | Live MT5 trading execution |
| `challenge_risk_manager.py` | 5ers challenge risk management |
| `challenge_rules.py` | 5ers challenge rule validation |

### Configuration

| Module | Purpose |
|--------|---------|
| `params/current_params.json` | Active trading parameters |
| `params/defaults.py` | Default parameter values |
| `params/params_loader.py` | Parameter loading utilities |
| `config.py` | General configuration |
| `broker_config.py` | Broker connection settings |

---

## Data Flow

### Optimization Flow
```
1. Load historical data (data/ohlcv/)
2. Optuna generates parameter combinations
3. strategy_core.simulate_trades() runs backtest
4. Calculate R-multiples and metrics
5. Store best parameters in params/
6. Validate with H1 realistic simulation
```

### Live Trading Flow
```
1. Load params/current_params.json
2. Connect to MT5 via broker_config.py
3. Fetch real-time candles
4. strategy_core generates signals
5. main_live_bot executes trades
6. 5-TP exit system manages positions
```

---

## Key Classes

### StrategyParams (strategy_core.py)
```python
@dataclass
class StrategyParams:
    # Confluence
    min_confluence: int = 5
    min_quality_factors: int = 3
    
    # 5 TP R-Multiples
    atr_tp1_multiplier: float = 0.6
    atr_tp2_multiplier: float = 1.2
    atr_tp3_multiplier: float = 2.0
    atr_tp4_multiplier: float = 2.5
    atr_tp5_multiplier: float = 3.5
    
    # 5 Close Percentages
    tp1_close_pct: float = 0.10
    tp2_close_pct: float = 0.10
    tp3_close_pct: float = 0.15
    tp4_close_pct: float = 0.20
    tp5_close_pct: float = 0.45
    
    # Risk
    risk_per_trade_pct: float = 0.6
    trail_activation_r: float = 0.65
```

### H1TradeSimulator (tradr/backtest/h1_trade_simulator.py)
```python
class H1TradeSimulator:
    """Simulates trades hour-by-hour matching main_live_bot behavior"""
    
    def simulate_trade(self, trade: dict, h1_data: pd.DataFrame) -> dict:
        """Returns P&L matching 5-TP exit logic"""
```

### ScalingConfig (scripts/validate_h1_realistic.py)
```python
@dataclass
class ScalingConfig:
    base_risk_pct: float = 0.006        # 0.6% base
    confluence_scale_per_point: float = 0.15  # ±15% per point
    streak_scale_per_trade: float = 0.05      # ±5% per trade
    min_risk_pct: float = 0.002         # 0.2% minimum
    max_risk_pct: float = 0.012         # 1.2% maximum
```

---

## Directory Structure

```
botcreativehub/
├── strategy_core.py              # Core strategy + 5-TP system
├── ftmo_challenge_analyzer.py    # Optimization engine
├── main_live_bot.py              # Live trading
├── indicators.py                 # Technical indicators
│
├── params/
│   ├── current_params.json       # Active parameters
│   ├── defaults.py               # Default values
│   └── params_loader.py          # Load utilities
│
├── scripts/
│   ├── validate_h1_realistic.py  # H1 realistic validator
│   └── download_*.py             # Data downloaders
│
├── tradr/
│   ├── backtest/
│   │   └── h1_trade_simulator.py # H1 trade simulation
│   └── indicators/               # Indicator modules
│
├── data/
│   ├── ohlcv/                    # Historical OHLCV data
│   └── sr_levels/                # Support/Resistance levels
│
├── ftmo_analysis_output/
│   ├── TPE/                      # TPE optimization results
│   ├── NSGA/                     # NSGA-II results
│   ├── VALIDATE/                 # Validation runs
│   └── hourly_validator/         # H1 simulation results
│
└── docs/                         # Documentation
```

---

## Symbol Handling

### Internal Format (OANDA)
- Uses underscores: `EUR_USD`, `XAU_USD`, `US30_USD`
- Used in data files and internal processing

### MT5 Format (Broker)
- No underscores: `EURUSD`, `XAUUSD`, `US30`
- Used for live trading execution

### Conversion
```python
from symbol_mapping import to_mt5_symbol, to_oanda_symbol

mt5_sym = to_mt5_symbol("EUR_USD")  # Returns "EURUSD"
oanda_sym = to_oanda_symbol("EURUSD")  # Returns "EUR_USD"
```

---

## Multi-Timeframe Architecture

### Timeframes Used
| Timeframe | Purpose |
|-----------|---------|
| Weekly | Trend direction, major S/R levels |
| Daily | Trade signals, entry timing |
| H4 | Confirmation (optional) |
| H1 | Live bot execution granularity |

### Look-Ahead Bias Prevention
```python
# Always slice HTF data before current candle timestamp
htf_candles = _slice_htf_by_timestamp(weekly_candles, current_daily_dt)
```

---

## Validation Pipeline

### 1. Optimization (TPE/NSGA-II)
```bash
python ftmo_challenge_analyzer.py --single --trials 100
```

### 2. Standard Validation
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
```

### 3. H1 Realistic Validation
```bash
python scripts/validate_h1_realistic.py \
    --trades ftmo_analysis_output/VALIDATE/best_trades_final.csv \
    --balance 60000
```

---

## Performance Results (2023-2025)

| Metric | Value |
|--------|-------|
| Starting Balance | $60,000 |
| Final Balance | $1,160,462 |
| Net P&L | $1,100,462 |
| Return | +1,834% |
| Total Trades | 1,673 |
| Win Rate | 71.8% |
| Total R | +274.71R |

---

**Last Updated**: January 4, 2026
