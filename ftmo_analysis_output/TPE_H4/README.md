# TPE_H4 Optimization Results

## Timeframe Configuration
- **Entry TF**: H4 (4-Hour) - Primary execution timeframe
- **Confirmation TF**: H1 (1-Hour) - Lower TF for confirmation
- **Bias TF**: D1 (Daily) - Higher TF for trend bias
- **S/R TF**: W1 (Weekly) - Major S/R levels

## vs TPE (D1 Mode)
| Metric | D1 (TPE) | H4 (TPE_H4) |
|--------|----------|-------------|
| Entry TF | D1 | H4 |
| Expected Trades/Year | ~950 | ~3000-4000 |
| Avg Hold Time | 5-10 days | 1-3 days |
| ATR Multiplier | 1.0x | 0.4x |

## Usage
```bash
# Run H4 optimization
python ftmo_challenge_analyzer.py --mode TPE_H4 --trials 50

# Monitor progress
tail -f ftmo_analysis_output/TPE_H4/optimization.log
```

## Expected Differences
- **More trades**: H4 entries generate ~3-4x more signals than D1
- **Shorter holds**: Average trade duration 1-3 days vs 5-10 days
- **Smaller per-trade profit**: But potentially higher total profit due to volume
- **Different risk profile**: More frequent entries = different drawdown patterns

## Files
- `optimization.log` - Trial results and scores
- `best_params.json` - Best performing parameters
- `best_trades_training.csv` - Training period trades
- `best_trades_validation.csv` - Validation period trades  
- `best_trades_final.csv` - Full period trades
- `history/run_XXX/` - Archived runs with professional reports
