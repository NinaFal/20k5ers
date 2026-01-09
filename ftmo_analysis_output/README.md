# FTMO Optimization Output Directory Structure

## Directory Layout

```
ftmo_analysis_output/
├── TPE/                        # Single-objective TPE optimization runs
│   ├── run.log                  # Complete console output (all debug info)
│   ├── optimization.log        # Current run trial log (structured results)
│   ├── best_params.json        # ⭐ REAL-TIME best parameters (auto-updates!)
│   ├── best_trades_*.csv       # Best trades from current run
│   ├── monthly_stats.csv       # Monthly performance breakdown
│   ├── symbol_performance.csv  # Per-symbol statistics
│   ├── professional_backtest_report.txt  # Detailed performance report
│   ├── analysis_summary_*.txt  # Run summaries with timestamps
│   └── history/                # Archived runs
│       ├── run_001/            # First optimization run
│       │   ├── optimization.log
│       │   ├── best_trades_training.csv
│       │   ├── best_trades_validation.csv
│       │   ├── best_trades_final.csv
│       │   ├── monthly_stats.csv
│       │   ├── symbol_performance.csv
│       │   ├── professional_backtest_report.txt
│       │   ├── analysis_summary_*.txt
│       │   └── best_params.json  ← Use these params to replicate results!
│       ├── run_002/
│       └── run_003/
│
├── NSGA/                       # Multi-objective NSGA-II optimization runs
│   └── (same structure as TPE)
│
└── VALIDATE/                   # Validation mode runs (no optimization)
    ├── best_trades_*.csv       # Trades from validation run
    ├── monthly_stats_final.csv
    ├── symbol_performance.csv
    ├── best_params.json        # Parameters used for validation
    ├── professional_backtest_report.txt
    ├── analysis_summary_*.txt
    └── history/                # Archived validation runs
        ├── val_2020_2022_001/  # First run: 2020-2022 period
        ├── val_2020_2022_002/  # Second run: same period
        └── val_2018_2020_001/  # Different period
```

## File Descriptions

### Current Run Files
- **run.log**: Complete console output with all debug info, asset processing, trial details
- **optimization.log**: Real-time trial results (score, R, win rate, profit) - structured format
- **best_params.json**: ⭐ **REAL-TIME best parameters** (auto-updates during optimization!)
  - Updates immediately when new best trial is found
  - Contains: trial number, best score, all parameters
  - Can be monitored with: `watch -n 5 cat ftmo_analysis_output/TPE/best_params.json`
  - Example:
    ```json
    {
      "trial_number": 13,
      "best_score": 273.18,
      "parameters": {
        "tp1_r_multiple": 0.8,
        "tp2_r_multiple": 1.5,
        "tp3_r_multiple": 4.0,
        "partial_exit_at_1r": 1.0,
        "risk_per_trade_pct": 0.55
      }
    }
    ```
- **best_trades_*.csv**: All trades from the best trial
  - `_training.csv`: In-sample period (2023-01-01 to 2024-09-30)
  - `_validation.csv`: Out-of-sample period (2024-10-01 to present)
  - `_final.csv`: Full period (entire 2023-2025)
- **monthly_stats.csv**: Monthly breakdown of trades, wins, profit
- **symbol_performance.csv**: Per-symbol: trades, win rate, profit
- **best_params.json**: Optimized parameters with metadata

### History Directory
Each `run_XXX/` directory contains a complete snapshot of an optimization run:
- All CSV files with trade data
- optimization.log with trial history
- professional_backtest_report.txt with detailed metrics
- analysis_summary_*.txt with run summaries
- **best_params.json** with the exact parameters used

### VALIDATE Directory (New in Dec 2025)
For validation mode runs (`--validate` flag):
- `val_YYYY_YYYY_XXX/` naming format (start year, end year, run number)
- Contains same files as optimization runs
- Used for testing parameters on different date ranges without optimization

## Using Historical Runs

### Analyzing Past Runs
```bash
# View parameters from run_003
cat ftmo_analysis_output/TPE/history/run_003/best_params.json

# Compare trades between runs
diff ftmo_analysis_output/TPE/history/run_001/best_trades_final.csv \
     ftmo_analysis_output/TPE/history/run_002/best_trades_final.csv

# Extract best score from each run
grep "🏆 NEW BEST" ftmo_analysis_output/TPE/history/*/optimization.log
```

### Applying Parameters to Live Bot
```bash
# Copy parameters from a specific run to live bot config
cp ftmo_analysis_output/TPE/history/run_005/best_params.json params/current_params.json
```

## Archiving Strategy

When an optimization run completes:
1. Current run's files are **copied** to `history/run_XXX/`
2. Run number is automatically incremented (run_001 → run_002 → run_003...)
3. Original files remain in current directory for quick access
4. All historical data is preserved for analysis

This ensures:
- ✅ Clean trial numbering per run
- ✅ Complete history of all optimization experiments
- ✅ Easy parameter recovery and comparison
- ✅ Current best is always in `TPE/` or `NSGA/` directory
- ✅ Reproducible results

## Tips

**Find best performing run:**
```bash
# Show best score from each run
for dir in ftmo_analysis_output/TPE/history/run_*/; do
    echo -n "$(basename $dir): "
    jq -r '.best_score // "N/A"' "$dir/best_params.json" 2>/dev/null || echo "No params"
done
```

**Compare validation performance:**
```bash
# Extract validation metrics from each run
grep "Validation" ftmo_analysis_output/TPE/history/*/optimization.log
```

**Archive cleanup (if needed):**
```bash
# Keep only last 10 runs (delete older)
cd ftmo_analysis_output/TPE/history/
ls -dt run_* | tail -n +11 | xargs rm -rf
```

## Validation Mode

Test existing parameters on different date ranges:

```bash
# Test parameters on 2020-2022 data
python ftmo_challenge_analyzer.py --validate --start 2020-01-01 --end 2022-12-31

# Use specific parameters file
python ftmo_challenge_analyzer.py --validate --start 2020-01-01 --end 2022-12-31 --params-file ftmo_analysis_output/TPE/history/run_006/best_params.json
```

**View validation results:**
```bash
# List all validation runs
ls ftmo_analysis_output/VALIDATE/history/

# Compare validation R across periods
for dir in ftmo_analysis_output/VALIDATE/history/val_*/; do
    echo -n "$(basename $dir): "
    grep "Total R" "$dir/professional_backtest_report.txt" 2>/dev/null | head -1 || echo "N/A"
done
```
