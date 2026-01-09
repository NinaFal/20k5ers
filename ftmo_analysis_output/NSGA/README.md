# NSGA-II Multi-Objective Optimization Results

This directory contains results from NSGA-II (Non-dominated Sorting Genetic Algorithm II) multi-objective optimization runs.

## What is NSGA-II?

NSGA-II optimizes **multiple objectives simultaneously** without combining them into a single score:
- **Total R**: Maximize total return
- **Sharpe Ratio**: Maximize risk-adjusted returns
- **Win Rate**: Maximize percentage of winning trades

Instead of finding one "best" solution, NSGA-II finds a **Pareto frontier** of non-dominated solutions where improving one objective requires sacrificing another.

## How to Run NSGA-II Optimization

```bash
# Basic usage (5 trials)
python ftmo_challenge_analyzer.py --multi

# With specific trial count
python ftmo_challenge_analyzer.py --multi --trials 50

# With symbol exclusion
python ftmo_challenge_analyzer.py --multi --trials 100 --exclude-symbols CAD_CHF
```

## Output Structure

```
NSGA/
├── best_trades_training.csv      # Best solution (composite score)
├── best_trades_validation.csv
├── best_trades_final.csv
├── monthly_stats_final.csv
├── symbol_performance.csv
├── best_params.json              # Best balanced parameters
├── professional_backtest_report.txt
├── optimization.log              # Trial-by-trial results
├── run.log                       # Complete debug output
└── history/
    ├── run_001/                  # First optimization run
    ├── run_002/                  # Second run
    └── run_003/                  # Third run
```

## NSGA vs TPE Comparison

| Feature | NSGA-II (--multi) | TPE (default) |
|---------|-------------------|---------------|
| Objectives | 3 (R, Sharpe, WR) | 1 (Composite Score) |
| Output | Pareto frontier | Single best |
| Selection | Balanced composite | Highest score |
| Use Case | Explore trade-offs | Fast convergence |
| Trials Needed | 50-100+ | 20-50 |

## Interpreting Pareto Results

After optimization, you'll see the Pareto frontier:

```
Trial    Total R    Sharpe    Win Rate    Trades
#5       +85.2      1.95      52.3%       843
#12      +102.1     1.72      49.1%       921
#23      +95.8      2.15      48.7%       801
```

**Selection Criteria:**
- Best composite score = 0.40×R_score + 0.35×Sharpe_score + 0.25×WR_score
- Normalized to ~1.0 range for balanced weighting

## Tips for Multi-Objective Optimization

**When to use NSGA-II:**
- Exploring parameter sensitivity
- Finding balanced strategies (not just max profit)
- Understanding trade-offs between metrics
- When you have time for longer runs (50+ trials)

**When to use TPE:**
- Quick parameter tuning
- Focused on single metric optimization
- Limited computational budget
- Initial strategy development

**Hybrid approach:**
```bash
# 1. Fast exploration with TPE
python ftmo_challenge_analyzer.py --single --trials 20

# 2. Refine with NSGA-II
python ftmo_challenge_analyzer.py --multi --trials 50
```

## Configuration

Edit `params/optimization_config.json` to change:
- Database path
- Trial count defaults
- Optimization mode toggles
- ADX regime filter settings
