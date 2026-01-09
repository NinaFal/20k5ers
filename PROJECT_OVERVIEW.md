# Project Overview - 5ers 60K High Stakes Trading Bot

## What This Project Does

This is a **production-ready automated trading bot** that trades forex, indices, and commodities on MetaTrader 5 (MT5) for the **5ers 60K High Stakes** prop firm challenge.

### Key Validated Results (January 2026)

**Equivalence Test: 97.6% Match Rate** - The live bot generates the same trades as the TPE backtest.

| Metric | Fixed Risk | With Compounding |
|--------|------------|------------------|
| **Starting Balance** | $60,000 | $60,000 |
| **Final Balance** | $310,553 | $3,203,619 |
| **Total Profit** | $250,553 | $3,143,619 |
| **Return** | +418% | +5,239% |
| **Trades** | 1,779 | 1,777 |
| **Win Rate** | 72.3% | 72.3% |
| **Total R** | +696.03R | +696.03R |

**5ers Compliance Verified:**
- Max Total DD: 7.75% (limit 10%) ✅
- Max Daily DD: 3.80% (limit 5%) ✅
- DD Margin: 1.20% with safety halt at 3.5%

---

## How It Works

### 1. Signal Generation
The bot scans 34 trading instruments daily at 22:05 UTC (after NY close) looking for high-probability setups based on:
- Multi-timeframe trend alignment (Monthly → Weekly → Daily → H4)
- Support/Resistance levels
- Fibonacci retracements
- Price action patterns
- Confluence scoring (minimum 5 factors)

### 2. Trade Entry
When a setup has enough "confluence" (multiple factors aligning), the bot:
- Calculates entry price, stop loss, and 5 take profit levels
- Places a pending order or enters immediately via MT5
- Sizes position based on 0.6% account risk per trade (dynamic lot sizing)

### 3. Trade Management (5-TP System)
The bot uses 5 take profit levels with partial exits:

| Level | Target | Close % | What Happens |
|-------|--------|---------|--------------|
| TP1 | 0.6R | 10% | Close 10%, move SL to breakeven |
| TP2 | 1.2R | 10% | Close 10%, trail SL |
| TP3 | 2.0R | 15% | Close 15%, trail SL |
| TP4 | 2.5R | 20% | Close 20%, trail SL |
| TP5 | 3.5R | 45% | Close remaining 45% |

> ⚠️ **CRITICAL**: The strategy uses 5 TPs. Never reduce to 3 TPs - it breaks exit calculations!

### 4. Risk Management (3-Tier System)
The live bot implements DDD (Daily DrawDown) safety:

| Tier | Daily DD | Action |
|------|----------|--------|
| Warning | ≥2.0% | Log warning, no action |
| Reduce | ≥3.0% | Reduce risk: 0.6% → 0.4% |
| Halt | ≥3.5% | Halt new trades until next day |

**Total DrawDown (TDD):**
- Static from initial balance ($60K → stop-out at $54K)
- NOT trailing (5ers rule, unlike FTMO)
- Maximum loss = $6,000 from starting balance

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
└─────────────────────────────────┘     └────────────────────────────────┘
```

---

## Core Files

### Trading Logic
| File | Purpose |
|------|---------|
| `strategy_core.py` | All trading logic: signals, 5-TP exits, `simulate_trades()` |
| `main_live_bot.py` | Live trading on MT5 with dynamic lot sizing |
| `challenge_risk_manager.py` | DDD/TDD enforcement, AccountSnapshot |
| `ftmo_config.py` | 5ers challenge configuration |

### Optimization & Validation
| File | Purpose |
|------|---------|
| `ftmo_challenge_analyzer.py` | Optimize and validate parameters |
| `scripts/validate_h1_realistic.py` | Simulate exact live bot behavior |
| `scripts/test_equivalence_v2.py` | Verify live bot = TPE backtest |

### Parameters
| File | Purpose |
|------|---------|
| `params/current_params.json` | Active trading parameters |
| `params/defaults.py` | Default parameter values |
| `params/params_loader.py` | Load/merge utilities |

---

## How to Run

### Validate Current Parameters
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
```

### Run Equivalence Test
```bash
python scripts/test_equivalence_v2.py --start 2023-01-01 --end 2025-12-31
```

### Run 5ers Compliance Simulation (with compounding)
```bash
python scripts/test_equivalence_v2.py --start 2023-01-01 --end 2025-12-31 --include-commissions
```

### Run Live Bot (Windows with MT5)
```bash
python main_live_bot.py
```

---

## 5ers Challenge Rules

| Rule | Requirement |
|------|-------------|
| Account Size | $60,000 |
| Step 1 Target | 8% = $4,800 |
| Step 2 Target | 5% = $3,000 |
| Max Total Drawdown | 10% = $6,000 (stop-out at $54,000) |
| Daily Drawdown | 5% (5ers tracks this!) |
| Min Profitable Days | 3 |

**Important**: 5ers DOES track daily drawdown (5% limit), contrary to earlier documentation.

---

## Expected Performance

Based on validated backtests with 5ers rules:

| Timeframe | Expected Return |
|-----------|-----------------|
| Per Month | ~$30,000-50,000 profit (with compounding) |
| Step 1 (8%) | 1-2 weeks |
| Step 2 (5%) | 1 week |
| Total Challenge | 2-3 weeks |

---

## Output Structure

```
ftmo_analysis_output/
├── VALIDATE/              # TPE validation results
│   ├── best_trades_final.csv
│   └── history/           # Historical runs
├── hourly_validator/      # H1 realistic simulation
├── TPE/                   # TPE optimization
└── NSGA/                  # NSGA-II optimization

analysis/
├── SESSION_JAN05_2026_RESULTS.md  # Latest validation session
└── h1_validation_results.json
```

---

## Key Test Results (January 5, 2026)

### Equivalence Test
```
TPE Validate: 1,779 trades
Live Bot:     1,737 trades matched (97.6%)
```

### 5ers Compliance Simulation (2023-2025)
```
Starting Balance:     $60,000
Final Balance:        $3,203,619
Net Profit:           $3,143,619
Return:               5,239%
Max Total DD:         7.75% (limit 10%) ✅
Max Daily DD:         3.80% (limit 5%) ✅
Trades Blocked by DD: 21
```

### Configuration Applied
```python
# ftmo_config.py FIVEERS_CONFIG
daily_loss_warning_pct = 0.020   # 2.0%
daily_loss_reduce_pct = 0.030    # 3.0%
daily_loss_halt_pct = 0.035      # 3.5%
max_total_dd_pct = 0.10          # 10%
```

---

## Technical Details

### Data
- Historical data in `data/ohlcv/` (D1, H1 timeframes)
- 34 trading instruments (forex pairs, gold, indices)
- Data range: 2003-2025
- Format: OANDA style (`EUR_USD`, `XAU_USD`)

### Symbol Mapping
- **Internal/Data**: OANDA format (`EUR_USD`, `XAU_USD`)
- **MT5 Execution**: Broker format (`EURUSD`, `XAUUSD`)
- Use `symbol_mapping.py` for conversions

---

## Important Notes

### The 5-TP System is Critical
The strategy uses 5 take profit levels. Attempts to simplify to 3 TPs broke the exit calculations. Always maintain all 5 levels:
- `atr_tp1_multiplier` through `atr_tp5_multiplier`
- `tp1_close_pct` through `tp5_close_pct`

### Live Bot = TPE Backtest
The equivalence test confirms 97.6% match rate between:
- `ftmo_challenge_analyzer.py --validate` (TPE backtest)
- `main_live_bot.py` signal generation (live bot)

### Dynamic Lot Sizing
The live bot uses dynamic lot sizing based on current balance:
- Fixed 0.6% risk per trade
- As balance grows, lot sizes grow
- Results in compounding effect

---

**Last Updated**: January 5, 2026
**Validated By**: Equivalence Test (97.6%), 5ers Compliance Simulation
