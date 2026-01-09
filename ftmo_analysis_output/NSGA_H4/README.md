# NSGA_H4 Optimization Results

## Timeframe Configuration  
- **Entry TF**: H4 (4-Hour) - Primary execution timeframe
- **Confirmation TF**: H1 (1-Hour) - Lower TF for confirmation
- **Bias TF**: D1 (Daily) - Higher TF for trend bias
- **S/R TF**: W1 (Weekly) - Major S/R levels

## Multi-Objective Optimization
NSGA-II Pareto optimization with H4 entries, optimizing for:
1. **Total R** (profitability)
2. **Sharpe Ratio** (risk-adjusted returns)
3. **Win Rate** (consistency)

## vs NSGA (D1 Mode)
| Metric | D1 (NSGA) | H4 (NSGA_H4) |
|--------|-----------|--------------|
| Entry TF | D1 | H4 |
| Expected Trades/Year | ~950 | ~3000-4000 |
| Avg Hold Time | 5-10 days | 1-3 days |
| ATR Multiplier | 1.0x | 0.4x |
| Optimization | NSGA-II | NSGA-II |

## Usage
```bash
# Run H4 multi-objective optimization
python ftmo_challenge_analyzer.py --mode NSGA_H4 --trials 50

# Monitor progress
tail -f ftmo_analysis_output/NSGA_H4/optimization.log
```

## Pareto Front
NSGA-II finds multiple optimal solutions on the Pareto front:
- High R, Lower Sharpe: Aggressive growth
- Balanced: Moderate R, good Sharpe
- Conservative: Lower R, high Sharpe & WR

## Files
- `optimization.log` - Trial results and Pareto ranks
- `best_params.json` - Best Pareto front solution
- `pareto_front.csv` - All non-dominated solutions
- `history/run_XXX/` - Archived runs with professional reports
