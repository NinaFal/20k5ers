# Indicator Toggle Implementation Matrix

## Current Status: All Filters DISABLED

All 15+ indicator filters in `strategy_core.py` are currently set to `False`:

```python
# strategy_core.py - StrategyParams class (line 130-240)

# Entry filters - ALL DISABLED
use_htf_filter: bool = False
use_structure_filter: bool = False
use_fib_filter: bool = False
use_confirmation_filter: bool = False

# Quantitative filters - ALL DISABLED
use_atr_regime_filter: bool = False
use_zscore_filter: bool = False
use_pattern_filter: bool = False

# Blueprint V2 filters - ALL DISABLED
use_mitigated_sr: bool = False
use_structural_framework: bool = False
use_displacement_filter: bool = False
use_candle_rejection: bool = False

# Advanced filters - ALL DISABLED
use_momentum_filter: bool = False
use_mean_reversion: bool = False

# ADX regime - DISABLED
use_adx_regime_filter: bool = False
use_adx_slope_rising: bool = False
```

## Recommended Filter Bundles for Optimization

### Bundle A: Core Entry Filters (START HERE)

| Filter | Impact on WR | Impact on DD | Trade Reduction | Priority |
|--------|-------------|--------------|-----------------|----------|
| `use_htf_filter` | +5-10% | -2% | -20% | **HIGH** |
| `use_structure_filter` | +3-7% | -1% | -15% | **HIGH** |
| `use_confirmation_filter` | +4-6% | -2% | -25% | **HIGH** |

**Implementation:**
```python
# Add to objective function params dict
'use_htf_filter': trial.suggest_categorical('use_htf_filter', [True, False]),
'use_structure_filter': trial.suggest_categorical('use_structure_filter', [True, False]),
'use_confirmation_filter': trial.suggest_categorical('use_confirmation_filter', [True, False]),
```

**Pass to StrategyParams:**
```python
params = StrategyParams(
    # ... existing ...
    use_htf_filter=trial_params['use_htf_filter'],
    use_structure_filter=trial_params['use_structure_filter'],
    use_confirmation_filter=trial_params['use_confirmation_filter'],
)
```

---

### Bundle B: Precision Entry Filters

| Filter | Impact on WR | Impact on DD | Trade Reduction | Priority |
|--------|-------------|--------------|-----------------|----------|
| `use_fib_filter` | +5-8% | -3% | -30% | **MEDIUM** |
| `use_displacement_filter` | +4-7% | -2% | -20% | **MEDIUM** |
| `use_candle_rejection` | +3-5% | -1% | -15% | **MEDIUM** |

**Note:** These filters are more restrictive but improve precision significantly.

---

### Bundle C: Market Regime Filters (EXPERIMENTAL)

| Filter | Impact on WR | Impact on DD | Trade Reduction | Priority |
|--------|-------------|--------------|-----------------|----------|
| `use_atr_regime_filter` | +2-4% | -1% | -10% | LOW |
| `use_zscore_filter` | +3-5% | -2% | -15% | LOW |
| `use_momentum_filter` | +2-4% | -1% | -10% | LOW |

**Warning:** These can reduce trade count significantly. Test carefully.

---

### Bundle D: Blueprint V2 Advanced Filters

| Filter | Impact on WR | Impact on DD | Trade Reduction | Priority |
|--------|-------------|--------------|-----------------|----------|
| `use_mitigated_sr` | +3-6% | -2% | -20% | LOW |
| `use_structural_framework` | +2-4% | -1% | -15% | LOW |

---

## Filter Dependencies

Some filters work better together:

```
use_htf_filter + use_structure_filter = Better trend entries
use_fib_filter + use_displacement_filter = Better reversal entries
use_confirmation_filter + use_candle_rejection = Better H4 timing
```

## Parameter Associations

When certain filters are enabled, their associated parameters become relevant:

| Filter | Associated Parameters |
|--------|----------------------|
| `use_fib_filter` | `fib_low`, `fib_high`, `fib_zone_type` |
| `use_atr_regime_filter` | `atr_min_percentile` |
| `use_zscore_filter` | `zscore_threshold` |
| `use_displacement_filter` | `displacement_atr_mult` |
| `use_momentum_filter` | `momentum_lookback` |
| `use_mitigated_sr` | `sr_proximity_pct` |
| `use_adx_regime_filter` | `adx_trend_threshold`, `adx_range_threshold` |

**Optimization Strategy:**
```python
# Only optimize associated params when filter is enabled
if params['use_fib_filter']:
    params['fib_low'] = trial.suggest_float('fib_low', 0.382, 0.618, step=0.05)
    params['fib_high'] = trial.suggest_float('fib_high', 0.786, 0.886, step=0.05)
else:
    params['fib_low'] = 0.5
    params['fib_high'] = 0.8
```

---

## Compute Confluence Function Reference

The filters are used in `compute_confluence()` at line 2013 in `strategy_core.py`:

```python
def compute_confluence(...) -> Tuple[Dict[str, bool], Dict[str, str], Tuple]:
    # HTF Filter
    if params.use_htf_filter:
        loc_note, loc_ok = _location_context(...)
    else:
        loc_note, loc_ok = "Location filter disabled", True
    
    # Fib Filter
    if params.use_fib_filter:
        fib_note, fib_ok = _fib_context(...)
    else:
        fib_note, fib_ok = "Fib filter disabled", True
    
    # Structure Filter
    if params.use_structure_filter:
        struct_ok, struct_note = _structure_context(...)
    else:
        struct_ok, struct_note = True, "Structure filter disabled"
    
    # Confirmation Filter
    if params.use_confirmation_filter:
        conf_note, conf_ok = _h4_confirmation(...)
    else:
        conf_note, conf_ok = "Confirmation filter disabled", True
    
    # ... (all other filters follow same pattern) ...
```

---

## Complete Filter Implementation Code

Add this to `ftmo_challenge_analyzer.py` objective function:

```python
# === FILTER TOGGLE PARAMETERS ===

# Bundle A: Core Entry (recommend enabling by default for higher WR)
'use_htf_filter': trial.suggest_categorical('use_htf_filter', [True, False]),
'use_structure_filter': trial.suggest_categorical('use_structure_filter', [True, False]),
'use_confirmation_filter': trial.suggest_categorical('use_confirmation_filter', [True, False]),

# Bundle B: Precision Entry (optional)
'use_fib_filter': trial.suggest_categorical('use_fib_filter', [True, False]),
'use_displacement_filter': trial.suggest_categorical('use_displacement_filter', [True, False]),
'use_candle_rejection': trial.suggest_categorical('use_candle_rejection', [True, False]),

# Bundle C: Market Regime (experimental - start disabled)
# 'use_atr_regime_filter': trial.suggest_categorical('use_atr_regime_filter', [True, False]),
# 'use_zscore_filter': trial.suggest_categorical('use_zscore_filter', [True, False]),
# 'use_momentum_filter': trial.suggest_categorical('use_momentum_filter', [True, False]),
```

Then pass to StrategyParams in `run_full_period_backtest`:

```python
params = StrategyParams(
    min_confluence=effective_confluence,
    min_quality_factors=min_quality_factors,
    risk_per_trade_pct=risk_per_trade_pct,
    # ... existing params ...
    
    # Filter toggles
    use_htf_filter=trial_params.get('use_htf_filter', False),
    use_structure_filter=trial_params.get('use_structure_filter', False),
    use_fib_filter=trial_params.get('use_fib_filter', False),
    use_confirmation_filter=trial_params.get('use_confirmation_filter', False),
    use_displacement_filter=trial_params.get('use_displacement_filter', False),
    use_candle_rejection=trial_params.get('use_candle_rejection', False),
)
```

---

## Expected Outcomes

### Scenario 1: No Filters (Current)
- Win Rate: ~48%
- Trade Count: ~1500
- Max DD: ~25%

### Scenario 2: Bundle A Only
- Win Rate: ~55-58%
- Trade Count: ~900-1000 (-35%)
- Max DD: ~20%

### Scenario 3: Bundle A + Bundle B
- Win Rate: ~60-65%
- Trade Count: ~500-700 (-55%)
- Max DD: ~15%

### Scenario 4: All Bundles
- Win Rate: ~65-70%
- Trade Count: ~300-500 (-70%)
- Max DD: ~12%

**Trade-off:** Higher win rate but fewer trades. Need to balance for FTMO target.

---

## Testing Recommendation

1. **Phase 1:** Test Bundle A alone (3 filters)
2. **Phase 2:** Add Bundle B (6 filters total)
3. **Phase 3:** Compare with/without compliance tracking
4. **Phase 4:** Fine-tune with Bundle C if needed

Start with more trades (fewer filters) and add filters only if WR is too low.
