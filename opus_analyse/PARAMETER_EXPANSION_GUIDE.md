# Parameter Space Expansion Guide

## Prioritized Parameters for Optimization

### CRITICAL: Add These First (Max DD Reduction)

```python
# Add to ftmo_challenge_analyzer.py objective function (~line 1056)

# === FTMO COMPLIANCE PARAMETERS ===
'daily_loss_halt_pct': trial.suggest_float('daily_loss_halt_pct', 3.5, 4.5, step=0.1),
'max_total_dd_warning': trial.suggest_float('max_total_dd_warning', 7.0, 9.0, step=0.5),
'consecutive_loss_halt': trial.suggest_int('consecutive_loss_halt', 3, 6),
```

### HIGH: TP System Parameters

```python
# === TAKE PROFIT R-MULTIPLES ===
# Must maintain: TP1 < TP2 < TP3 < TP4 < TP5
'tp1_r_multiple': trial.suggest_float('tp1_r_multiple', 1.0, 2.0, step=0.25),
'tp2_r_multiple': trial.suggest_float('tp2_r_multiple', 2.0, 4.0, step=0.5),
'tp3_r_multiple': trial.suggest_float('tp3_r_multiple', 3.5, 6.0, step=0.5),
'tp4_r_multiple': trial.suggest_float('tp4_r_multiple', 5.0, 8.0, step=1.0),
'tp5_r_multiple': trial.suggest_float('tp5_r_multiple', 7.0, 12.0, step=1.0),

# === TAKE PROFIT CLOSE PERCENTAGES ===
# Sum of tp1+tp2+tp3+tp4 should be < 0.85 (tp5 gets remainder)
'tp1_close_pct': trial.suggest_float('tp1_close_pct', 0.10, 0.40, step=0.05),
'tp2_close_pct': trial.suggest_float('tp2_close_pct', 0.10, 0.25, step=0.05),
'tp3_close_pct': trial.suggest_float('tp3_close_pct', 0.10, 0.25, step=0.05),
'tp4_close_pct': trial.suggest_float('tp4_close_pct', 0.10, 0.30, step=0.05),
```

### HIGH: Filter Toggle Parameters

```python
# === ENTRY FILTER TOGGLES ===
# Each filter reduces trade count but increases win rate
'use_htf_filter': trial.suggest_categorical('use_htf_filter', [True, False]),
'use_structure_filter': trial.suggest_categorical('use_structure_filter', [True, False]),
'use_fib_filter': trial.suggest_categorical('use_fib_filter', [True, False]),
'use_confirmation_filter': trial.suggest_categorical('use_confirmation_filter', [True, False]),
'use_atr_regime_filter': trial.suggest_categorical('use_atr_regime_filter', [True, False]),
'use_displacement_filter': trial.suggest_categorical('use_displacement_filter', [True, False]),
'use_candle_rejection': trial.suggest_categorical('use_candle_rejection', [True, False]),
```

### MEDIUM: Position Sizing Parameters

```python
# === DYNAMIC POSITION SIZING ===
'use_dynamic_lot_sizing': trial.suggest_categorical('use_dynamic_lot_sizing', [True, False]),
'confluence_scale_per_point': trial.suggest_float('confluence_scale_per_point', 0.10, 0.25, step=0.05),
'max_confluence_multiplier': trial.suggest_float('max_confluence_multiplier', 1.2, 1.8, step=0.1),
'loss_streak_reduction_per_loss': trial.suggest_float('loss_streak_reduction_per_loss', 0.05, 0.15, step=0.05),
'equity_reduce_multiplier': trial.suggest_float('equity_reduce_multiplier', 0.6, 0.9, step=0.1),
```

### LOW: Fine-Tuning Parameters

```python
# === FINE TUNING ===
'cooldown_bars': trial.suggest_int('cooldown_bars', 0, 5),
'breakeven_trigger_r': trial.suggest_float('breakeven_trigger_r', 0.5, 1.5, step=0.25),
'zscore_threshold': trial.suggest_float('zscore_threshold', 1.0, 2.5, step=0.25),
'momentum_lookback': trial.suggest_int('momentum_lookback', 5, 20),
'sr_proximity_pct': trial.suggest_float('sr_proximity_pct', 0.01, 0.03, step=0.005),
'displacement_atr_mult': trial.suggest_float('displacement_atr_mult', 1.0, 2.5, step=0.25),
```

---

## Validation Constraints

Add these constraint checks after parameter generation:

```python
# After params dict is created, validate constraints:

# TP R-Multiple monotonic constraint
if not (params['tp1_r_multiple'] < params['tp2_r_multiple'] < params['tp3_r_multiple']):
    return -999999.0  # Invalid: TPs must be ascending

# TP Close percentage sum constraint
total_close = (params['tp1_close_pct'] + params['tp2_close_pct'] + 
               params['tp3_close_pct'] + params.get('tp4_close_pct', 0))
if total_close > 0.85:
    return -999999.0  # Invalid: Need remainder for TP5

# ADX threshold constraint
if params['adx_range_threshold'] >= params['adx_trend_threshold']:
    return -999999.0  # Invalid: Range threshold must be below trend

# Fib zone constraint  
if params['fib_zone_low'] >= params['fib_zone_high']:
    return -999999.0  # Invalid: Low must be below high
```

---

## Complete Updated Objective Function Template

```python
def objective_ftmo_v3(trial: optuna.Trial) -> float:
    """
    FTMO Challenge Optimizer - Version 3
    Expanded parameter space with compliance tracking.
    """
    
    # === CORE RISK PARAMETERS ===
    params = {
        'risk_per_trade_pct': trial.suggest_float('risk_per_trade_pct', 0.2, 1.0, step=0.1),
        'max_concurrent_trades': trial.suggest_int('max_concurrent_trades', 3, 10),
    }
    
    # === CONFLUENCE THRESHOLDS ===
    params.update({
        'min_confluence_score': trial.suggest_int('min_confluence_score', 2, 6),
        'min_quality_factors': trial.suggest_int('min_quality_factors', 1, 3),
        'trend_min_confluence': trial.suggest_int('trend_min_confluence', 3, 6),
        'range_min_confluence': trial.suggest_int('range_min_confluence', 2, 5),
    })
    
    # === ADX REGIME PARAMETERS ===
    params.update({
        'adx_trend_threshold': trial.suggest_int('adx_trend_threshold', 18, 30),
        'adx_range_threshold': trial.suggest_int('adx_range_threshold', 12, 22),
    })
    
    # === ATR PARAMETERS ===
    params.update({
        'atr_trail_multiplier': trial.suggest_float('atr_trail_multiplier', 1.0, 3.0, step=0.25),
        'atr_vol_ratio_range': trial.suggest_float('atr_vol_ratio_range', 0.5, 1.0, step=0.1),
        'atr_min_percentile': trial.suggest_float('atr_min_percentile', 30.0, 70.0, step=10.0),
        'atr_sl_multiplier': trial.suggest_float('atr_sl_multiplier', 1.0, 2.5, step=0.25),
    })
    
    # === EXIT STRATEGY PARAMETERS ===
    params.update({
        'partial_exit_at_1r': trial.suggest_categorical('partial_exit_at_1r', [True, False]),
        'partial_exit_pct': trial.suggest_float('partial_exit_pct', 0.25, 0.75, step=0.1),
        'trail_activation_r': trial.suggest_float('trail_activation_r', 1.0, 3.0, step=0.5),
    })
    
    # === NEW: TAKE PROFIT SYSTEM ===
    params.update({
        'tp1_r_multiple': trial.suggest_float('tp1_r_multiple', 1.0, 2.0, step=0.25),
        'tp2_r_multiple': trial.suggest_float('tp2_r_multiple', 2.0, 4.0, step=0.5),
        'tp3_r_multiple': trial.suggest_float('tp3_r_multiple', 3.5, 6.0, step=0.5),
        'tp1_close_pct': trial.suggest_float('tp1_close_pct', 0.10, 0.40, step=0.05),
        'tp2_close_pct': trial.suggest_float('tp2_close_pct', 0.10, 0.25, step=0.05),
        'tp3_close_pct': trial.suggest_float('tp3_close_pct', 0.10, 0.25, step=0.05),
    })
    
    # === NEW: FILTER TOGGLES ===
    params.update({
        'use_htf_filter': trial.suggest_categorical('use_htf_filter', [True, False]),
        'use_structure_filter': trial.suggest_categorical('use_structure_filter', [True, False]),
        'use_fib_filter': trial.suggest_categorical('use_fib_filter', [True, False]),
        'use_confirmation_filter': trial.suggest_categorical('use_confirmation_filter', [True, False]),
        'use_displacement_filter': trial.suggest_categorical('use_displacement_filter', [True, False]),
    })
    
    # === NEW: FTMO COMPLIANCE ===
    params.update({
        'daily_loss_halt_pct': trial.suggest_float('daily_loss_halt_pct', 3.5, 4.5, step=0.1),
        'consecutive_loss_halt': trial.suggest_int('consecutive_loss_halt', 3, 6),
    })
    
    # === SEASONALITY ===
    params.update({
        'volatile_asset_boost': trial.suggest_float('volatile_asset_boost', 1.0, 2.0, step=0.2),
        'summer_risk_multiplier': trial.suggest_float('summer_risk_multiplier', 0.4, 1.0, step=0.2),
        'fib_zone_low': trial.suggest_float('fib_zone_low', 0.5, 0.65, step=0.05),
        'fib_zone_high': trial.suggest_float('fib_zone_high', 0.75, 0.9, step=0.05),
    })
    
    # === VALIDATE CONSTRAINTS ===
    if not (params['tp1_r_multiple'] < params['tp2_r_multiple'] < params['tp3_r_multiple']):
        return -999999.0
    
    if params['adx_range_threshold'] >= params['adx_trend_threshold']:
        return -999999.0
    
    total_close = params['tp1_close_pct'] + params['tp2_close_pct'] + params['tp3_close_pct']
    if total_close > 0.75:
        return -999999.0
    
    # ... rest of objective function ...
```

---

## Search Space Size Comparison

| Configuration | Parameters | Search Space Size | Trials Recommended |
|---------------|------------|-------------------|-------------------|
| Current (V2) | 19 | ~10^12 | 100-500 |
| Proposed (V3) | 35 | ~10^20 | 500-2000 |
| Full (V4) | 45+ | ~10^25 | 2000+ |

**Recommendation:** Start with V3 (35 params) for balance of exploration and efficiency.
