# NSGA-II Validation Results

Test NSGA-II optimized parameters on different date ranges without re-optimization.

## How to Run NSGA-II Validation

```bash
# Basic usage (uses best_params.json from NSGA optimization)
python ftmo_challenge_analyzer.py --validate --multi --start 2020-01-01 --end 2022-12-31

# With specific NSGA parameters file
python ftmo_challenge_analyzer.py --validate --multi --start 2018-01-01 --end 2020-12-31 --params-file ftmo_analysis_output/NSGA/history/run_001/best_params.json

# Test different periods
python ftmo_challenge_analyzer.py --validate --multi --start 2015-01-01 --end 2018-12-31
python ftmo_challenge_analyzer.py --validate --multi --start 2019-01-01 --end 2021-12-31
```

## Parameters

| Flag | Description | Example |
|------|-------------|---------|
| `--validate` | Enable validation mode (required) | |
| `--multi` | Use NSGA-II validation directory (required) | |
| `--start` | Start date (YYYY-MM-DD) | `2020-01-01` |
| `--end` | End date (YYYY-MM-DD) | `2022-12-31` |
| `--params-file` | Path to NSGA parameters JSON | `best_params.json` |
| `--exclude-symbols` | Exclude specific symbols | `CAD_CHF,CHF_JPY` |

## Output Structure

```
VALIDATE_NSGA/
├── best_trades_training.csv      # 70% of period
├── best_trades_validation.csv    # 30% of period
├── best_trades_final.csv         # Full period
├── monthly_stats.csv
├── symbol_performance.csv
└── history/
    ├── val_2020_2022_001/        # First run: 2020-2022
    │   ├── analysis_summary_*.txt
    │   ├── professional_backtest_report.txt
    │   ├── best_params.json
    │   ├── best_trades_*.csv
    │   ├── monthly_stats.csv
    │   └── symbol_performance.csv
    ├── val_2020_2022_002/        # Second run: same period
    ├── val_2018_2020_001/        # Different period
    └── val_2015_2018_001/        # Another period
```

## NSGA vs TPE Validation

| Aspect | VALIDATE_NSGA (--multi) | VALIDATE (default) |
|--------|-------------------------|---------------------|
| Parameters Source | NSGA-II optimization | TPE optimization |
| Expected Traits | Balanced metrics | Highest composite score |
| Use Case | Test Pareto solutions | Test single-best params |
| Directory | ftmo_analysis_output/VALIDATE_NSGA/ | ftmo_analysis_output/VALIDATE/ |

## Validation Results Summary

| Period | Parameters | Total R | Trades | Win Rate | Sharpe | Profit |
|--------|------------|---------|--------|----------|--------|--------|
| TBD | NSGA run_001 | TBD | TBD | TBD | TBD | TBD |

## Tips

**Compare NSGA vs TPE on same period:**
```bash
# Test TPE parameters
python ftmo_challenge_analyzer.py --validate --start 2020-01-01 --end 2022-12-31 --params-file ftmo_analysis_output/TPE/history/run_006/best_params.json

# Test NSGA parameters  
python ftmo_challenge_analyzer.py --validate --multi --start 2020-01-01 --end 2022-12-31 --params-file ftmo_analysis_output/NSGA/history/run_001/best_params.json
```

**Test Pareto frontier solutions:**
```bash
# If you saved multiple Pareto solutions, test each one
python ftmo_challenge_analyzer.py --validate --multi --start 2020-01-01 --end 2022-12-31 --params-file nsga_trial_5.json
python ftmo_challenge_analyzer.py --validate --multi --start 2020-01-01 --end 2022-12-31 --params-file nsga_trial_12.json
python ftmo_challenge_analyzer.py --validate --multi --start 2020-01-01 --end 2022-12-31 --params-file nsga_trial_23.json
```

**Test strategy robustness across regimes:**
```bash
# Pre-crypto era (2015-2017)
python ftmo_challenge_analyzer.py --validate --multi --start 2015-01-01 --end 2017-12-31

# Crypto boom (2018-2020)
python ftmo_challenge_analyzer.py --validate --multi --start 2018-01-01 --end 2020-12-31

# COVID recovery (2021-2023)
python ftmo_challenge_analyzer.py --validate --multi --start 2021-01-01 --end 2023-12-31
```

## Expected Performance Characteristics

NSGA-II optimized parameters typically show:
- **More balanced metrics**: Sharpe/WR closer to training period
- **Lower max drawdown**: Better risk control
- **Smoother equity curve**: Less volatile returns
- **Better OOS generalization**: Pareto solutions avoid overfitting

Compare with TPE results in `../VALIDATE/` to see if multi-objective optimization provides better robustness.
