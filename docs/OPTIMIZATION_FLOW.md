# Unified Smart Optimization Flow

## Overview

This document describes the TPE/NSGA-II optimization flow with end-of-run validation for speed and robustness.

```
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 1: TPE/NSGA-II Optimization (Training Only)                  │
│ • Training: 2023-01-01 to 2024-09-30 (21 months in-sample)         │
│ • 25+ parameter search space (TP scaling, filters, ADX, etc.)      │
│ • FTMOComplianceTracker computes DD metrics (no trade filtering)   │
│ • Hard constraints: TP ordering, close-sum ≤85%, ADX thresholds    │
│ • No validation runs during optimization (speed optimization)       │
│ • Real-time best_params.json updates on each new best trial        │
│ • Output: Best training trial + study database                     │
│ • Time: ~1-2 hours for 100 trials                                  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Top-5 Trial Validation (OOS Check)                        │
│ • Validation: 2024-10-01 to 2025-12-26 (15 months out-of-sample)   │
│ • Select best OOS performer (highest validation R)                 │
│ • Time: ~10 minutes                                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Robustness Testing (Best OOS Params)                      │
│ • Monte Carlo (500 sims): 95th percentile drawdown                 │
│ • Walk-Forward (22 windows): parameter stability                   │
│ • Time: ~15 minutes                                                │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Final Backtest & Export                                   │
│ • Full 2023-2025 backtest with best OOS parameters                 │
│ • Generate comprehensive CSV reports (all 34 symbols)              │
│ • Export to params/current_params.json + history archive           │
│ • Professional report with metrics breakdown                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Why This Design?

### Speed Optimization (10x faster than before)
- Training-only during exploration phase (TPE/NSGA-II)
- Validation only on top 5 candidates (not every best trial)
- Monte Carlo only on final winner
- Removed redundant backtests in callback

### Robustness Checks
- OOS validation prevents overfitting (2024-10 to 2025-12)
- Monte Carlo tests strategy under random trade order (500 simulations)
- Walk-forward validates parameter stability (22 rolling windows)
- All 34 symbols tested in final backtest

## Time Estimates

| Trials | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Total |
|--------|---------|---------|---------|---------|-------|
| 50     | 1h      | 5m      | 10m     | 5m      | ~1.5h |
| 100    | 2h      | 10m     | 15m     | 5m      | ~2.5h |
| 200    | 4h      | 10m     | 15m     | 5m      | ~4.5h |
| 500    | 10h     | 10m     | 15m     | 5m      | ~11h  |

## Usage

### Real-Time Monitoring (New Jan 2026)
```bash
# Monitor optimization progress
tail -f ftmo_analysis_output/TPE/run.log          # Complete output
tail -f ftmo_analysis_output/TPE/optimization.log # Trial results only

# Check current best parameters (auto-updates!)
cat ftmo_analysis_output/TPE/best_params.json
# Example output:
# {
#   "trial_number": 13,
#   "best_score": 273.18,
#   "parameters": {
#     "tp1_r_multiple": 0.8,
#     "tp2_r_multiple": 1.5,
#     "tp3_r_multiple": 4.0,
#     "partial_exit_at_1r": 1.0,
#     "risk_per_trade_pct": 0.55
#   }
# }

# Watch for updates in real-time
watch -n 5 cat ftmo_analysis_output/TPE/best_params.json
```

### NSGA-II Multi-Objective (Recommended for FTMO)
```bash
# Default: NSGA-II with smart validation (outputs to ftmo_analysis_output/NSGA/)
python ftmo_challenge_analyzer.py --multi --trials 100

# With ADX regime filtering enabled
python ftmo_challenge_analyzer.py --multi --adx --trials 100

# Background run (recommended: use helper script)
./run_optimization.sh --multi --trials 200

# Manual background run
nohup python ftmo_challenge_analyzer.py --multi --adx --trials 200 > ftmo_analysis_output/NSGA/run.log 2>&1 &
```

### TPE Single-Objective (Faster, simpler scoring)
```bash
# TPE optimization (outputs to ftmo_analysis_output/TPE/)
python ftmo_challenge_analyzer.py --single --trials 100

# With ADX regime filtering
python ftmo_challenge_analyzer.py --single --adx --trials 100

# Background run (recommended: use helper script)
./run_optimization.sh --single --trials 100
```

### Output Structure
```
ftmo_analysis_output/
├── NSGA/                          # Multi-objective runs
│   ├── run.log                    # Complete console output (when using run_optimization.sh)
│   ├── optimization.log           # Trial results only (via OutputManager)
│   ├── best_trades_training.csv
│   ├── best_trades_validation.csv
│   ├── best_trades_final.csv
│   ├── monthly_stats.csv
│   ├── symbol_performance.csv
│   └── optimization_report.csv
└── TPE/                           # Single-objective runs
    ├── run.log                    # Complete console output (when using run_optimization.sh)
    ├── optimization.log           # Trial results only (via OutputManager)
    ├── best_trades_training.csv
    ├── best_trades_validation.csv
    ├── best_trades_final.csv
    ├── monthly_stats.csv
    ├── symbol_performance.csv
    └── optimization_report.csv
```

**Log Files Explained:**
- `run.log`: Complete output including "Processing asset X/37", warnings, all debug info
- `optimization.log`: Clean trial results only (score, R, win rate, profit)

---

## Validation Mode (New in Dec 2025)

Test existing parameters on different date ranges without running optimization.

### Usage
```bash
# Test parameters on 2020-2022 data
python ftmo_challenge_analyzer.py --validate --start 2020-01-01 --end 2022-12-31

# Use specific parameters file
python ftmo_challenge_analyzer.py --validate --start 2020-01-01 --end 2022-12-31 --params-file params/run_006_best.json
```

### How It Works
1. Loads parameters from `best_params.json` (or specified file)
2. Splits the date range: 70% training, 30% validation
3. Runs backtests on training, validation, and full periods
4. Exports results to `ftmo_analysis_output/VALIDATE/`

### Output Structure
```
ftmo_analysis_output/VALIDATE/
├── best_trades_training.csv
├── best_trades_validation.csv
├── best_trades_final.csv
├── monthly_stats_final.csv
├── symbol_performance.csv
├── best_params.json
├── professional_backtest_report.txt
├── analysis_summary_*.txt
└── history/
    ├── val_2020_2022_001/      # First validation run for 2020-2022
    ├── val_2020_2022_002/      # Second run same period
    └── val_2018_2020_001/      # Different period
```

### Use Cases
- **Strategy validation**: Test if parameters generalize to unseen data
- **Market regime testing**: Check performance across different market conditions
- **Historical analysis**: Backtest on pre-2023 data without re-optimization
- **Parameter comparison**: Compare multiple parameter sets on same period
