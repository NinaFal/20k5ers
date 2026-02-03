# Backtest System

**Last Updated**: February 3, 2026

## Overview

The backtest system uses `main_live_bot_backtest.py` which is an **exact copy** of `main_live_bot.py` but uses CSV data instead of real MT5 connection.

---

## Files

| File | Purpose |
|------|---------|
| `src/main_live_bot_backtest.py` | Backtest version of live bot |
| `src/csv_mt5_simulator.py` | CSV-based MT5 simulator |
| `optimize_main_live_bot.py` | Optuna parameter optimizer |

---

## Commands

### Run Backtest
```bash
python backtest/src/main_live_bot_backtest.py --start 2023-01-01 --end 2025-12-31 --balance 20000
```

### Run Optimization
```bash
python backtest/optimize_main_live_bot.py --trials 100 --start 2024-01-01 --end 2024-12-31
```

---

## Output Directories

| Directory | Contents |
|-----------|----------|
| `output/` | Backtest results, trades CSV |
| `optimization_results/` | Optuna study results |
| `logs/` | Backtest logs |

---

**Last Updated**: February 3, 2026
