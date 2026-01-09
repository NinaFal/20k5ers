# Baseline Analysis (Finalized)

**Date**: 2025-12-31  
**Scope**: 12-year robustness validation (2014-2025) with finalized parameters (risk 0.6%).

## Executive Summary
- ✅ Production-ready; consistent performance across 4 periods with ~48.6% win rate.
- ✅ FTMO compliant: daily DD <3.8%, total DD <3% vs limits 5%/10%.
- ✅ FTMO speed: Step 1 (10%) in 18 dagen, Step 2 (5%) in 10 dagen — total 28 dagen.
- Parameters locked in `best_params.json` and `params/current_params.json`.

## 12-Year Validation Results
| Period | Total R | Profit | Win Rate |
|--------|---------|--------|----------|
| 2014-2016 | +672.7R | $807,219 | 48.7% |
| 2017-2019 | +679.2R | $815,002 | 48.7% |
| 2020-2022 | +662.4R | $794,919 | 48.3% |
| 2023-2025 | +752.0R | $902,410 | 48.8% |
| **Total** | **+2,766.3R** | **$3,319,550** | **~48.6%** |

## Parameter Snapshot (Dec 31, 2025)
- risk_per_trade_pct: 0.6
- min_confluence / score: 2
- min_quality_factors: 3
- adx_trend_threshold: 22.0 / adx_range_threshold: 11.0
- trend_min_confluence: 6 / range_min_confluence: 2
- atr_trail_multiplier: 1.6; trail_activation_r: 0.8; atr_min_percentile: 42; atr_volatility_ratio: 0.95
- TP ladder: 1.7R / 2.6R / 5.4R with closes 38% / 16% / 30%; partial_exit_at_1r: true; partial_exit_pct: 0.7
- FTMO guards: daily_loss_halt_pct 3.8; max_total_dd_warning 7.9; consecutive_loss_halt 10
- Filters: HTF/structure/confirmation/fib/displacement/candle_rejection all disabled (baseline)

## Compliance & Risk
- Daily DD observed <3.8% (limit 5%)
- Total DD observed <3% (limit 10%)
- Consecutive loss halt: 10 (soft guard, never triggered in validation)
- Risk sizing: 0.6% per trade; partials at 1R reduce tail risk

## Conclusions
- Strategy is **production-ready** with stable performance across regimes.
- No period-specific degradation; validation win rate peaks at 53.1% (2025 split).
- Maintain current parameter set; next iterations can explore enabling selective filters if market regime changes.

## Next Steps
- Deploy to live MT5 (Windows VM) with current params.
- Monitor live DD vs. FTMO limits; keep streak halt at 10.
- Optional: periodic revalidation quarterly; consider enabling structure/confirmation filters if volatility regime shifts.
