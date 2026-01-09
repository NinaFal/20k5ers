# AI Assistant Guide - 5ers 60K High Stakes Trading Bot

## Project Overview

This is a **production-ready automated trading bot** for **5ers 60K High Stakes** Challenge accounts.

### Key Facts
- **Platform**: MetaTrader 5 (MT5)
- **Account Size**: $60,000
- **Strategy**: 5-TP Confluence System with multi-timeframe analysis
- **Validated**: 97.6% equivalence between backtest and live bot (January 2026)

---

## Current State (January 5, 2026)

### ✅ Production Ready
The system is fully validated with the following results:

```
EQUIVALENCE TEST (2023-2025):
- TPE Validate Trades: 1,779
- Live Bot Matched:    1,737 (97.6%)
- Status: Systems are EQUIVALENT ✅

5ERS COMPLIANCE SIMULATION:
- Starting Balance: $60,000
- Final Balance:    $3,203,619 (+5,239%)
- Max Total DD:     7.75% (limit 10%) ✅
- Max Daily DD:     3.80% (limit 5%) ✅
- DD Margin:        1.20% with 3.5% halt
```

### 5-TP Exit System
The strategy uses **5 Take Profit levels** (NOT 3):

| Level | R-Multiple | Close % |
|-------|------------|---------|
| TP1 | 0.6R | 10% |
| TP2 | 1.2R | 10% |
| TP3 | 2.0R | 15% |
| TP4 | 2.5R | 20% |
| TP5 | 3.5R | 45% |

> ⚠️ **CRITICAL**: Never reduce to 3 TPs - it breaks the exit logic!

### DDD Safety System (3-Tier)

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning only |
| Reduce | ≥3.0% | Reduce risk 0.6% → 0.4% |
| Halt | ≥3.5% | Stop new trades until next day |

---

## Core Files

### Primary Files
| File | Lines | Purpose |
|------|-------|---------|
| `strategy_core.py` | ~3,100 | Trading strategy - signals, 5-TP exits, `simulate_trades()` |
| `ftmo_challenge_analyzer.py` | ~2,900 | Optimization, validation, backtesting |
| `main_live_bot.py` | ~1,500 | Live MT5 trading with dynamic lot sizing |
| `challenge_risk_manager.py` | ~800 | DDD/TDD enforcement, AccountSnapshot |
| `ftmo_config.py` | ~100 | 5ers challenge configuration |

### Parameters
| File | Purpose |
|------|---------|
| `params/current_params.json` | Active optimized parameters |
| `params/defaults.py` | Default values (includes tp4/tp5) |
| `params/params_loader.py` | Load/merge parameters |

### Validation & Testing
| File | Purpose |
|------|---------|
| `scripts/test_equivalence_v2.py` | Verify live bot = TPE backtest |
| `scripts/validate_h1_realistic.py` | H1 trade simulation |
| `tradr/backtest/h1_trade_simulator.py` | H1 simulation engine |

---

## Key Functions

### strategy_core.py

```python
# Generate trading signals
signals = generate_signals(candles, symbol, params, monthly_candles, weekly_candles, h4_candles)

# Simulate trades through historical data (MAIN BACKTEST FUNCTION)
trades = simulate_trades(candles, symbol, params, monthly_candles, weekly_candles, h4_candles)

# Compute trade levels (entry, SL, TP1-TP5)
note, is_valid, entry, sl, tp1, tp2, tp3 = compute_trade_levels(daily_candles, direction, params)
```

### challenge_risk_manager.py

```python
# Get account snapshot with risk info
snapshot = manager.get_account_snapshot()

# Check if trading allowed
can_trade, reason = manager.check_trading_allowed()

# AccountSnapshot fields (as of Jan 5, 2026)
@dataclass
class AccountSnapshot:
    balance: float
    equity: float
    floating_pnl: float
    margin_used: float
    free_margin: float
    total_dd_pct: float
    daily_dd_pct: float
    is_stopped_out: bool
    timestamp: datetime
    total_risk_usd: float     # Added Jan 5, 2026
    total_risk_pct: float     # Added Jan 5, 2026
    open_positions: int       # Added Jan 5, 2026
```

### ftmo_config.py

```python
# 5ers Configuration (Updated Jan 5, 2026)
class FIVEERS_CONFIG:
    starting_balance = 60000
    profit_target_step1_pct = 0.08    # 8% = $4,800
    profit_target_step2_pct = 0.05    # 5% = $3,000
    max_total_dd_pct = 0.10           # 10% = $6,000
    max_daily_dd_pct = 0.05           # 5% = $3,000
    daily_loss_warning_pct = 0.020    # 2.0% - log warning
    daily_loss_reduce_pct = 0.030     # 3.0% - reduce risk
    daily_loss_halt_pct = 0.035       # 3.5% - halt trading
    min_profitable_days = 3
```

---

## Commands

### Run Equivalence Test
```bash
python scripts/test_equivalence_v2.py --start 2023-01-01 --end 2025-12-31
```

### Run 5ers Compliance Simulation
```bash
python scripts/test_equivalence_v2.py --start 2023-01-01 --end 2025-12-31 --include-commissions
```

### Run TPE Validation
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
```

### Run H1 Simulation
```bash
python scripts/validate_h1_realistic.py --trades ftmo_analysis_output/VALIDATE/best_trades_final.csv --balance 60000
```

### Run Optimization
```bash
python ftmo_challenge_analyzer.py --single --trials 100  # TPE
python ftmo_challenge_analyzer.py --multi --trials 100   # NSGA-II
```

### Check Status
```bash
python ftmo_challenge_analyzer.py --status
```

---

## StrategyParams Dataclass

Key parameters in `strategy_core.py`:

```python
@dataclass
class StrategyParams:
    # Confluence
    min_confluence: int = 5
    min_quality_factors: int = 3
    
    # TP R-Multiples (5 levels - ALL REQUIRED)
    atr_tp1_multiplier: float = 0.6
    atr_tp2_multiplier: float = 1.2
    atr_tp3_multiplier: float = 2.0
    atr_tp4_multiplier: float = 2.5
    atr_tp5_multiplier: float = 3.5
    
    # Close Percentages (5 levels - ALL REQUIRED)
    tp1_close_pct: float = 0.10
    tp2_close_pct: float = 0.10
    tp3_close_pct: float = 0.15
    tp4_close_pct: float = 0.20
    tp5_close_pct: float = 0.45
    
    # Trailing Stop
    trail_activation_r: float = 0.65
    
    # Risk
    risk_per_trade_pct: float = 0.6
```

---

## Data Structure

### OHLCV Data
Located in `data/ohlcv/`:
```
{SYMBOL}_{TIMEFRAME}_{START}_{END}.csv
Examples:
- EUR_USD_D1_2003_2025.csv
- SPX500USD_H1_2023_2025.csv
```

### Output Structure
```
ftmo_analysis_output/
├── VALIDATE/                      # TPE validation results
│   ├── best_trades_final.csv      # All validated trades
│   ├── best_params.json           # Current best parameters
│   └── history/                   # Historical runs
│       └── val_2023_2025_007/     # Latest validation
├── hourly_validator/              # H1 realistic simulation
├── TPE/                           # TPE optimization results
└── NSGA/                          # NSGA-II optimization results

analysis/
├── SESSION_JAN05_2026_RESULTS.md  # Latest session archive
├── h1_validation_results.json     # H1 validation data
└── h1_validation_results.csv      # H1 validation trades
```

---

## Important Conventions

### Symbol Format
- **Internal/Data**: OANDA format (`EUR_USD`, `XAU_USD`)
- **MT5 Execution**: Broker format (`EURUSD`, `XAUUSD`)
- Always use `symbol_mapping.py` for conversions

### Parameters - Never Hardcode
```python
# ✅ CORRECT
from params.params_loader import load_strategy_params
params = load_strategy_params()

# ❌ WRONG
MIN_CONFLUENCE = 5  # Don't hardcode
```

### Multi-Timeframe Data
Always prevent look-ahead bias:
```python
# Slice HTF data to reference timestamp
htf_candles = _slice_htf_by_timestamp(weekly_candles, current_daily_dt)
```

---

## 5ers Challenge Rules

| Rule | Limit |
|------|-------|
| Max Total Drawdown | 10% below starting balance ($54K stop-out) |
| Max Daily Drawdown | 5% from day start ($3K max daily loss) |
| Step 1 Target | 8% = $4,800 |
| Step 2 Target | 5% = $3,000 |
| Min Profitable Days | 3 |

**Key Difference from FTMO:**
- 5ers TDD is STATIC from initial balance (not trailing like FTMO)
- Example: Start $60K, grow to $80K, drop to $55K = SAFE (above $54K)

---

## Recent History

### January 5, 2026
- **Equivalence Test**: 97.6% match between TPE and live bot ✅
- **5ers Compliance**: Max DD 7.75%, Daily DD 3.80% with commissions ✅
- **Profit Projection**: $3.2M with compounding (2023-2025)
- **DDD Settings**: Updated to 3.5%/3.0%/2.0% (halt/reduce/warning)
- **Bug Fix**: Added `total_risk_usd`, `total_risk_pct`, `open_positions` to AccountSnapshot

### January 4, 2026
- **REVERTED** to 5-TP system (3-TP removal broke exit logic)
- H1 realistic validator added
- Validation confirmed: +696R (D1), +274R (H1 realistic)

---

## What NOT to Do

1. ❌ **Never remove TP4/TP5** - breaks exit calculations
2. ❌ **Never change exit logic** without full validation
3. ❌ **Never hardcode parameters** in source files
4. ❌ **Never use trailing TDD** - 5ers uses static TDD
5. ❌ **Never ignore DDD** - 5ers DOES track daily drawdown

---

## Quick Reference

### Latest Validation: January 5, 2026
- TPE Backtest: 1,779 trades, +696.03R, 72.3% WR
- Equivalence: 97.6% match with live bot
- 5ers Compliance: TDD 7.75%, DDD 3.80% (both within limits)
- Profit with Compounding: $3,203,619 (from $60K)

### Key Files Modified (Jan 5, 2026)
- `ftmo_config.py` - DDD settings (3.5%/3.0%/2.0%)
- `challenge_risk_manager.py` - AccountSnapshot fields
- `main_live_bot.py` - getattr fallback for total_risk_usd

### Key Commits
- `61bdcac` - REVERT: Restore 5-TP system
- `2d1979c` - H1 validator results added

---

**Last Updated**: January 5, 2026
**Validated By**: Equivalence Test (97.6%), 5ers Compliance Simulation
