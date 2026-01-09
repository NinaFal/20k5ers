# Final Validation Report (Production Release)

**Date**: 2025-12-31  
**Account**: FTMO 200K  
**Risk**: 0.6% per trade  
**Parameters**: See `best_params.json` / `params/current_params.json`

## Executive Summary
- 12-year backtest (2014-2025) shows **+2,766.3R**, **$3,319,550** profit, **~48.6% win rate**.
- FTMO compliant: daily DD <3.8% (limit 5%), total DD <3% (limit 10%).
- Challenge speed: Step 1 (10%) in 18 dagen; Step 2 (5%) in 10 dagen; total 28 dagen.
- Strategy is **production-ready** with stable performance across regimes.

## 12-Year Results
| Period | Total R | Profit | Win Rate |
|--------|---------|--------|----------|
| 2014-2016 | +672.7R | $807,219 | 48.7% |
| 2017-2019 | +679.2R | $815,002 | 48.7% |
| 2020-2022 | +662.4R | $794,919 | 48.3% |
| 2023-2025 | +752.0R | $902,410 | 48.8% |
| **Total** | **+2,766.3R** | **$3,319,550** | **~48.6%** |

## Per-Period Notes
- **2014-2016**: Validation WR 55.0% (highest), strong range-trend mix; DD <3.8%.
- **2017-2019**: Balanced regime; DD minimal (<3%); stable WR 49.6% in validation split.
- **2020-2022**: Pandemic/volatility stress; WR 48.4% validation; DD held <3.8%.
- **2023-2025**: Latest regime; WR 53.1% validation split; best R (+752.0) and profit.

## Symbol Performance (high level)
- Strength: Majors and gold remained consistent; indices contributed steady R without DD spikes.
- Weakness: No single symbol caused compliance breach; streak halt (10) not triggered.

## FTMO Compliance
- Daily loss limit: Observed <3.8% vs. 5% limit (halt at 3.8%).
- Total drawdown: Observed <3% vs. 10% limit (emergency at 7%).
- Risk control: 0.6% risk per trade; partial exit 70% at 1R reduces tail risk.

## Conclusion
- **Go-Live Ready**: Deploy current params to live MT5 bot.
- Maintain risk at 0.6%; keep filters disabled (baseline) unless regime shifts.
- Revalidate quarterly; consider enabling structure/confirmation filters if volatility or chop increases.
