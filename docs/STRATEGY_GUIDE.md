# Trading Strategy Guide

## Strategy Overview

Multi-timeframe confluence-based trading strategy for the **5ers 60K High Stakes Challenge**.

### Key Characteristics
- **Confluence-based entries**: Minimum 5 confluence points required
- **Quality factor filtering**: Minimum 3 quality factors
- **5-TP exit system**: Partial closes at 5 levels (0.6R to 3.5R)
- **Dynamic trailing stop**: Activates after TP1

---

## Entry Conditions

### Confluence Scoring

Each factor adds to the confluence score:

| Factor | Description |
|--------|-------------|
| Weekly Trend | Price above/below weekly EMA |
| Daily Trend | Price above/below daily EMA |
| RSI Zone | Not overbought/oversold |
| Bollinger Position | Price at bands |
| S/R Level | Near support/resistance |
| EMA Alignment | Multiple EMAs aligned |
| Volume Confirmation | Above average volume |
| Candle Pattern | Bullish/bearish patterns |

### Quality Factors

Additional confirmation signals:
- Strong momentum
- Clean price action
- No divergences
- Proper market structure

### Entry Logic
```python
if confluence >= params.min_confluence:
    if quality_factors >= params.min_quality_factors:
        generate_signal()
```

---

## Exit System (5-TP)

### Take Profit Levels

| Level | R-Multiple | Close % |
|-------|------------|---------|
| TP1 | 0.6R | 10% |
| TP2 | 1.2R | 10% |
| TP3 | 2.0R | 15% |
| TP4 | 2.5R | 20% |
| TP5 | 3.5R | 45% |

### Trailing Stop
- **Activation**: After TP1 hit
- **Breakeven**: Move SL to entry after TP1
- **Progressive**: Trail behind each TP level

### Example Trade
```
Entry: 1.1000, SL: 1.0950 (50 pips risk)

TP1: 1.1030 (0.6R) → Close 10%
TP2: 1.1060 (1.2R) → Close 10%
TP3: 1.1100 (2.0R) → Close 15%
TP4: 1.1125 (2.5R) → Close 20%
TP5: 1.1175 (3.5R) → Close 45%

Maximum R = 2.555R if all TPs hit
```

---

## Risk Management

### Position Sizing
```python
risk_per_trade_pct: float = 0.006  # 0.6% per trade
```

### 5ers Challenge Limits
| Rule | Value |
|------|-------|
| Max Total DD | 10% ($6,000 from $60K) |
| Daily DD | Not tracked by 5ers |
| Step 1 Target | 8% ($4,800) |
| Step 2 Target | 5% ($3,000) |
| Min Profitable Days | 3 |

### Safety Mechanisms (H1 Validator)
- Safety close at 4.2% daily drawdown
- Confluence scaling: ±15% per point from 5
- Win/loss streak scaling: ±5% per trade
- Risk limits: 0.2% minimum, 1.2% maximum

---

## Instruments Traded

### Forex Majors
- EUR_USD, GBP_USD, USD_JPY, USD_CHF
- AUD_USD, NZD_USD, USD_CAD

### Crosses
- EUR_GBP, EUR_JPY, GBP_JPY
- AUD_JPY, CAD_JPY, CHF_JPY

### Commodities
- XAU_USD (Gold)
- XAG_USD (Silver)

### Indices
- US30_USD (Dow Jones)
- SPX500_USD (S&P 500)
- NAS100_USD (NASDAQ)

---

## Parameters

### Current Parameters (params/current_params.json)
```json
{
    "min_confluence": 5,
    "min_quality_factors": 3,
    "atr_tp1_multiplier": 0.6,
    "atr_tp2_multiplier": 1.2,
    "atr_tp3_multiplier": 2.0,
    "atr_tp4_multiplier": 2.5,
    "atr_tp5_multiplier": 3.5,
    "tp1_close_pct": 0.10,
    "tp2_close_pct": 0.10,
    "tp3_close_pct": 0.15,
    "tp4_close_pct": 0.20,
    "tp5_close_pct": 0.45,
    "risk_per_trade_pct": 0.006,
    "trail_activation_r": 0.65
}
```

### Loading Parameters
```python
from params.params_loader import load_strategy_params
params = load_strategy_params()

# Access values
confluence = params.min_confluence
tp1 = params.atr_tp1_multiplier
```

---

## Validation Results

### H1 Realistic Simulation (2023-2025)
```
Starting Balance:  $60,000
Final Balance:     $1,160,462
Net P&L:           $1,100,462
Return:            +1,834%
Total Trades:      1,673
Winners:           1,201
Win Rate:          71.8%
Total R:           +274.71R
Safety Closes:     22
DD Breaches:       0
```

### Monthly Performance
- Average monthly R: ~11.4R
- Worst month: ~-3.5R
- Best month: ~35R

---

## Optimization

### TPE (Tree-structured Parzen Estimator)
```bash
python ftmo_challenge_analyzer.py --single --trials 100
```
Best for single-objective optimization (maximize R).

### NSGA-II (Multi-Objective)
```bash
python ftmo_challenge_analyzer.py --multi --trials 100
```
Optimizes multiple objectives: R, win rate, drawdown.

### Validation
```bash
python ftmo_challenge_analyzer.py --validate \
    --start 2023-01-01 --end 2025-12-31
```

### H1 Realistic Test
```bash
python scripts/validate_h1_realistic.py \
    --trades ftmo_analysis_output/VALIDATE/best_trades_final.csv \
    --balance 60000
```

---

## Common Commands

### Check Status
```bash
python ftmo_challenge_analyzer.py --status
```

### Run Full Validation
```bash
python ftmo_challenge_analyzer.py --validate --start 2023-01-01 --end 2025-12-31
python scripts/validate_h1_realistic.py --trades ftmo_analysis_output/VALIDATE/best_trades_final.csv
```

### View Results
```bash
cat ftmo_analysis_output/hourly_validator/best_trades_final_realistic_summary.json
```

---

## Critical Rules

1. **NEVER reduce from 5 TPs to 3 TPs** - This breaks exit logic
2. **NEVER hardcode parameters** - Always use params_loader
3. **NEVER use look-ahead bias** - Slice HTF data properly
4. **Always validate with H1 simulation** - Matches live bot behavior

---

**Last Updated**: January 4, 2026
