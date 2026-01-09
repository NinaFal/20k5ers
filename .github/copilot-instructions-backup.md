# AI Assistant Instructions - 5ers Trading Bot

## Project Overview

Automated MetaTrader 5 trading bot for **5ers 60K High Stakes** Challenge accounts.

### Current State (January 5, 2026)
- **Status**: ✅ Production Ready
- **Validation**: 97.6% equivalence between backtest and live bot
- **5ers Compliance**: Max TDD 7.75%, Max DDD 3.80% (both within limits)
- **Profit Projection**: $3.2M with compounding (2023-2025)
- **Exit System**: 5 Take Profit levels (NOT 3)

---

## Architecture

```
┌─────────────────────────────────┐     ┌────────────────────────────────┐
│   OPTIMIZER (Any Platform)      │     │  LIVE BOT (Windows VM + MT5)   │
│                                  │     │                                 │
│  ftmo_challenge_analyzer.py      │────▶│  main_live_bot.py              │
│  - Optuna TPE / NSGA-II          │     │  - Loads params/current*.json  │
│  - Backtesting 2003-2025         │     │  - Real-time MT5 execution     │
│  - H1 realistic validation       │     │  - 5 Take Profit levels        │
│                                  │     │  - Dynamic lot sizing          │
│                                  │     │  - DDD/TDD safety              │
└─────────────────────────────────┘     └────────────────────────────────┘
```

---

## Key Modules

| File | Purpose |
|------|---------|
| `strategy_core.py` | Trading strategy - 5-TP system, signals, `simulate_trades()` |
| `ftmo_challenge_analyzer.py` | Optimization & validation engine |
| `main_live_bot.py` | Live MT5 trading with dynamic lot sizing |
| `challenge_risk_manager.py` | DDD/TDD enforcement, AccountSnapshot |
| `ftmo_config.py` | 5ers challenge configuration |
| `scripts/test_equivalence_v2.py` | Verify live bot = TPE backtest |
| `scripts/validate_h1_realistic.py` | H1 realistic simulation |
| `params/current_params.json` | Active optimized parameters |
| `params/defaults.py` | Default parameter values (includes tp4/tp5) |

---

## 5-TP Exit System (CRITICAL)

The strategy uses **5 Take Profit levels**. This is critical - DO NOT reduce to 3 TPs.

| Level | R-Multiple | Close % |
|-------|------------|---------|
| TP1 | 0.6R | 10% |
| TP2 | 1.2R | 10% |
| TP3 | 2.0R | 15% |
| TP4 | 2.5R | 20% |
| TP5 | 3.5R | 45% |

**Trailing Stop**:
- Activated after TP1 hit
- Moves to breakeven after TP1
- After TP2+: `trailing_sl = previous_tp + 0.5 * risk`

---

## DDD Safety System (3-Tier)

The live bot implements Daily DrawDown protection:

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning only |
| Reduce | ≥3.0% | Reduce risk: 0.6% → 0.4% |
| Halt | ≥3.5% | Stop new trades until next day |

**5ers Rules**:
- 5ers DOES track daily drawdown (5% limit)
- TDD is STATIC from initial balance (not trailing like FTMO)
- $60K account → stop-out at $54K (regardless of peak equity)

---

## Validated Performance (January 5, 2026)

### Equivalence Test Results
```
TPE Validate Trades: 1,779
Live Bot Matched:    1,737 (97.6%)
Status: Systems are EQUIVALENT ✅
```

### 5ers Compliance Simulation (2023-2025)
```json
{
  "starting_balance": 60000,
  "final_balance": 3203619,
  "net_pnl": 3143619,
  "return_pct": 5239,
  "total_trades": 1777,
  "win_rate": 72.3,
  "max_total_dd_pct": 7.75,
  "max_daily_dd_pct": 3.80,
  "trades_blocked_by_ddd": 21
}
```

---

## Commands

### Equivalence Test
```bash
python scripts/test_equivalence_v2.py --start 2023-01-01 --end 2025-12-31
```

### 5ers Compliance Simulation
```bash
python scripts/test_equivalence_v2.py --start 2023-01-01 --end 2025-12-31 --include-commissions
```

### TPE Validation
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
```

### H1 Realistic Simulation
```bash
python scripts/validate_h1_realistic.py --trades ftmo_analysis_output/VALIDATE/best_trades_final.csv --balance 60000
```

### Optimization
```bash
python ftmo_challenge_analyzer.py --single --trials 100  # TPE
python ftmo_challenge_analyzer.py --multi --trials 100   # NSGA-II
```

### Status
```bash
python ftmo_challenge_analyzer.py --status
```

---

## Critical Conventions

### Symbol Format
- **Internal/Data**: OANDA format with underscores (`EUR_USD`, `XAU_USD`)
- **MT5 Execution**: Broker format (`EURUSD`, `XAUUSD`)
- Use `symbol_mapping.py` for conversions

### Parameters - NEVER Hardcode
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
htf_candles = _slice_htf_by_timestamp(weekly_candles, current_daily_dt)
```

---

## StrategyParams Key Fields

```python
@dataclass
class StrategyParams:
    # Confluence
    min_confluence: int = 5
    min_quality_factors: int = 3
    
    # TP R-Multiples (5 levels)
    atr_tp1_multiplier: float = 0.6
    atr_tp2_multiplier: float = 1.2
    atr_tp3_multiplier: float = 2.0
    atr_tp4_multiplier: float = 2.5
    atr_tp5_multiplier: float = 3.5
    
    # Close Percentages (5 levels)
    tp1_close_pct: float = 0.10
    tp2_close_pct: float = 0.10
    tp3_close_pct: float = 0.15
    tp4_close_pct: float = 0.20
    tp5_close_pct: float = 0.45
    
    # Risk
    risk_per_trade_pct: float = 0.6
    trail_activation_r: float = 0.65
```

---

## FIVEERS_CONFIG Key Fields

```python
class FIVEERS_CONFIG:
    starting_balance = 60000
    profit_target_step1_pct = 0.08    # 8% = $4,800
    profit_target_step2_pct = 0.05    # 5% = $3,000
    max_total_dd_pct = 0.10           # 10% = $6,000
    max_daily_dd_pct = 0.05           # 5% = $3,000
    daily_loss_warning_pct = 0.020    # 2.0%
    daily_loss_reduce_pct = 0.030     # 3.0%
    daily_loss_halt_pct = 0.035       # 3.5%
    min_profitable_days = 3
```

---

## 5ers Challenge Rules

| Rule | Limit |
|------|-------|
| Account Size | $60,000 |
| Max Total DD | 10% below start ($54K stop-out) - STATIC |
| Max Daily DD | 5% from day start ($3K max daily loss) |
| Step 1 Target | 8% = $4,800 |
| Step 2 Target | 5% = $3,000 |
| Min Profitable Days | 3 |

**Key Difference from FTMO**: TDD is STATIC from initial balance, NOT trailing.

---

## File Structure

```
botcreativehub/
├── strategy_core.py              # 5-TP system, signals
├── ftmo_challenge_analyzer.py    # Optimization & validation
├── main_live_bot.py              # Live MT5 trading
├── challenge_risk_manager.py     # DDD/TDD enforcement
├── ftmo_config.py                # 5ers configuration
├── params/
│   ├── current_params.json       # Active parameters
│   ├── defaults.py               # Default values (tp1-tp5)
│   └── params_loader.py          # Load utilities
├── scripts/
│   ├── test_equivalence_v2.py    # Equivalence test
│   └── validate_h1_realistic.py  # H1 simulation
├── tradr/backtest/
│   └── h1_trade_simulator.py     # H1 trade engine
├── data/ohlcv/                   # Historical data
├── analysis/
│   └── SESSION_JAN05_2026_RESULTS.md  # Latest session
└── ftmo_analysis_output/         # Results
```

---

## What NOT to Do

1. ❌ **Never reduce from 5 TPs to 3 TPs** - breaks exit logic
2. ❌ **Never hardcode parameters** - use params_loader
3. ❌ **Never change exit logic** without full validation
4. ❌ **Never use look-ahead bias** - always slice HTF data
5. ❌ **Never use trailing TDD** - 5ers uses STATIC TDD
6. ❌ **Never ignore DDD** - 5ers DOES track daily drawdown (5% limit)

---

## Recent History

### January 5, 2026
- **Equivalence Test**: 97.6% match between TPE and live bot ✅
- **5ers Compliance**: Max TDD 7.75%, Max DDD 3.80% (within limits) ✅
- **Profit Projection**: $3.2M with compounding (2023-2025)
- **DDD Settings**: Updated to 3.5%/3.0%/2.0% (halt/reduce/warning)
- **Bug Fix**: Added `total_risk_usd`, `total_risk_pct`, `open_positions` to AccountSnapshot
- **Files Modified**: ftmo_config.py, challenge_risk_manager.py, main_live_bot.py

### January 4, 2026
- REVERTED to 5-TP system (3-TP removal broke exit logic)
- Added H1 realistic validation
- Confirmed +1,834% return over 2023-2025

### Key Commits
- `61bdcac` - REVERT: Restore 5-TP system
- `2d1979c` - Add H1 validator results

---

## Session Archives

- `analysis/SESSION_JAN05_2026_RESULTS.md` - Complete validation session
- `docs/SESSION_LOG_JAN04_2026.md` - 5-TP revert session

---

**Last Updated**: January 5, 2026
