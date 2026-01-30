# AI Assistant Guide - 5ers 20K Trading Bot

## Quick Reference

This document helps AI assistants understand the trading bot architecture quickly.

---

## System Overview

| Aspect | Value |
|--------|-------|
| **Platform** | MetaTrader 5 (MT5) |
| **Account** | 5ers 20K High Stakes |
| **Strategy** | 3-TP Confluence System |
| **Status** | ✅ Production Ready |

---

## Two-Level Backtest Architecture

**CRITICAL**: To backtest `main_live_bot.py`, you need TWO stages:

### Stage 1: Signal Generation
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
```
- Uses `compute_confluence()` from `strategy_core.py`
- Outputs: `trades CSV` with entry/SL/TP levels

### Stage 2: H1 Simulation  
```bash
python scripts/main_live_bot_backtest.py
```
- Simulates EXACTLY what `main_live_bot.py` does
- Entry queue, lot sizing at fill, 3-TP exits, DDD/TDD checks

**Result**: Both stages together = realistic backtest matching live bot

---

## Core Files

| File | Purpose |
|------|---------|
| `strategy_core.py` | Trading signals via `compute_confluence()` |
| `ftmo_challenge_analyzer.py` | `--validate` generates trades CSV |
| `scripts/main_live_bot_backtest.py` | H1 simulation with compounding |
| `main_live_bot.py` | Live MT5 trading |
| `params/current_params.json` | Optimized parameters |
| `challenge_risk_manager.py` | DDD/TDD safety |

---

## Trading Logic

### Entry Queue System
| Condition | Action |
|-----------|--------|
| Price ≤0.05R from entry | Market order |
| Price ≤0.3R from entry | Limit order |
| Price >0.3R from entry | Wait in queue (max 5 days) |

### 3-TP Exit System
| Level | R-Multiple | Close % | SL Action |
|-------|------------|---------|-----------|
| TP1 | 0.6R | 35% | Move to breakeven |
| TP2 | 1.2R | 30% | Trail to TP1+0.5R |
| TP3 | 2.0R | 35% | Close all |

### DDD Safety (3-Tier)
| Daily DD | Action |
|----------|--------|
| ≥2.0% | Warning |
| ≥3.0% | Reduce risk |
| ≥3.5% | Halt trading |

---

## Latest Performance

```
Starting Balance: $20,000
Final Balance:    $310,183
Return:           +1,451%
Trades:           871
Win Rate:         67.5%
Max TDD:          4.94% (limit 10%)
Max DDD:          3.61% (limit 5%)
```

---

## Key Rules

1. **Parameters**: Always use `params_loader.py`, never hardcode
2. **Lot Sizing**: Calculate at FILL moment, not signal time
3. **TDD**: STATIC from initial balance (not trailing)
4. **Backtest**: Run BOTH stages (validate + simulate)
5. **Symbols**: Internal = `EUR_USD`, MT5 = `EURUSD`

---

## File Locations

| Data | Location |
|------|----------|
| Historical data | `data/ohlcv/` |
| Parameters | `params/current_params.json` |
| Simulation results | `ftmo_analysis_output/SIMULATE_*/` |
| Logs | `logs/` |

---

**Last Updated**: January 20, 2026
