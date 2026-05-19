# AI Assistant Instructions - 5ers Trading Bot

## Project Overview

Automated MetaTrader 5 trading bot for **5ers 50K High Stakes** Challenge accounts.

### Current State (May 19, 2026)
- **Status**: ✅ Production Ready & Validated
- **Account**: $50,000 (5ers 50K High Stakes)
- **Latest Simulation**: $310,183 from $20K (+1,451%, 871 trades) — backtest ran on 20K, live bot now runs on 50K
- **5ers Compliance**: Max TDD 4.94%, Max DDD 3.61% (both within limits)
- **Exit System**: 5 Take Profit levels (see 5-TP Exit System below)
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
python backtest/src/main_live_bot_backtest.py --start 2023-01-01 --end 2025-12-31 --balance 50000
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

### Parameters — Twee bronnen, twee doelen

**BELANGRIJK**: Er zijn twee soorten parameters in dit project. Ken het verschil.

#### 1. Account-level risk limits → `config.py` + `challenge_rules.py`
Drawdown limieten, account grootte, dagelijkse verlieslimieten. Dit zijn vaste 5ers-regels.
```python
from config import ACCOUNT_SIZE, MAX_DAILY_LOSS_PCT, MAX_TOTAL_LOSS_PCT
# ACCOUNT_SIZE = 50000
# MAX_DAILY_LOSS_PCT = 0.05  → $2,500 max daily loss
# MAX_TOTAL_LOSS_PCT = 0.10  → $5,000 max drawdown, stop-out bij $45,000
```

#### 2. Strategie parameters → `params/current_params.json` (via `params_loader.py`)
ALLE trading parameters komen hieruit: risk per trade, confluence drempels, TP/SL levels, enz.
Dit bestand wordt overschreven door de optimizer. **Nooit hardcoden.**

```python
# ✅ CORRECT
from params.params_loader import load_strategy_params
params = load_strategy_params()
risk_pct = params.risk_per_trade_pct  # Huidig: 1.1%

# ❌ FOUT — config.py zegt 0.6% maar dat is slechts een fallback
risk_pct = 0.6
```

**Actuele waarden in `current_params.json` (mei 2026):**
- `risk_per_trade_pct`: **1.1%** → $550 per trade op $50K account
- `min_confluence`: 6
- `tp1_r_multiple`: 0.6R, `tp2_r_multiple`: 0.9R, ... t/m `tp5_r_multiple`: 3.5R

### Lot Sizing - At FILL Moment
```python
# Lot size berekend op het moment van FILL, niet bij signaalgeneratie
# Dit zorgt voor correcte compounding
lot_size = calculate_lot_size(
    balance=current_balance,        # Huidig saldo, niet saldo bij signaal
    risk_pct=params.risk_per_trade_pct,  # Uit current_params.json (1.1%)
    entry=fill_price,
    stop_loss=sl,
)
```

---

## 5ers Challenge Rules

| Rule | Limiet | Bedrag bij $50K |
|------|--------|-----------------|
| Account Size | $50,000 | — |
| Max Total DD | 10% van startbalans — STATIC | $5,000 max verlies, stop-out bij $45,000 |
| Max Daily DD | 5% van dagstart | $2,500 max daily loss |
| Step 1 Target | 8% | $4,000 |
| Step 2 Target | 5% | $2,500 |

**Key**: TDD is STATIC van initial balance ($50K), NIET trailing.

### Wat `config.py` WEL en NIET is
- ✅ `config.py` = account-level limieten (drawdown %, account size, DDD halt %)
- ❌ `config.py` is NIET de bron voor `risk_per_trade_pct` — dat staat in `current_params.json`
- De `RISK_PER_TRADE_PCT = 0.006` in `config.py` is een **fallback**, niet de actieve waarde

---

## What NOT to Do

1. ❌ **Never hardcode parameters** - use params_loader
2. ❌ **Never change exit logic** without full simulation
3. ❌ **Never use trailing TDD** - 5ers uses STATIC TDD
4. ❌ **Never calculate lot size at signal time** - use fill time balance
5. ❌ **Never run only Stage 1** - always run both validate AND simulate

---

**Last Updated**: May 19, 2026
