# FTMO Compliance Guide (Production)

**Date**: 2025-12-31  
**Account**: FTMO 200K Challenge  
**Strategy Risk**: 0.6% per trade

## FTMO Challenge Rules
- Phase 1 target: **+10%**
- Phase 2 target: **+5%**
- Max daily loss: **5%** (bot halts at 4.2%, observed <3.8%)
- Max total drawdown: **10%** (bot emergency at 7%, observed <3%)
- No weekend gaps/holding unless explicitly enabled (bot flat by design)

## Bot Compliance Mechanisms
- `daily_loss_halt_pct`: 3.8% (halts before FTMO 5% limit)
- `max_total_dd_warning`: 7.9% warning (emergency stop at 7%)
- `consecutive_loss_halt`: 10 (soft guard; not triggered in validation)
- Risk sizing: 0.6% per trade with partials at 1R to de-risk runners
- ADX/filters: conservative baseline (HTF/structure/confirmation/fib/displacement/candle rejection disabled) to avoid over-filtered zero-trade states

## Challenge Pass Strategy
- Use finalized params (`best_params.json` / `params/current_params.json`).
- Phase 1 (10%): Achieved in **18 dagen** (historical speed) at 0.6% risk.
- Phase 2 (5%): Achieved in **10 dagen**.
- Total pass time: **28 dagen**.
- Keep streak halt at 10 to prevent tilt during chop.

## Best Start Window
- Historical seasonality favors **Q2 (April-Juni)** for smoother trend cycles and lower whipsaw.

## Operational Checklist
- Load params via `params_loader.py` (no hardcoding).
- Verify `.env` for MT5 credentials; run `main_live_bot.py` on Windows VM with MT5.
- Monitor live DD vs. 3.8% daily / 7% total guards; halt if breached.
- Keep trade size capped by `risk_per_trade_pct`; partial_exit_at_1r=true lowers tail risk.

## References
- Parameters: `best_params.json`, `params/current_params.json`
- Validation runs: `ftmo_analysis_output/VALIDATE/history/val_2014_2016_002`, `val_2017_2019_002`, `val_2020_2022_002`, `val_2023_2025_001`
