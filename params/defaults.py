#!/usr/bin/env python3
"""
SINGLE SOURCE OF TRUTH for all trading parameters and their defaults.

This module is imported by:
- ftmo_challenge_analyzer.py (for saving after optimization)
- main_live_bot.py (for loading with validation)
- params_loader.py (for constructing StrategyParams)

DO NOT DUPLICATE THESE DEFAULTS ELSEWHERE!

CRITICAL: When adding new parameters:
1. Add to PARAMETER_DEFAULTS dict below
2. Add to StrategyParams dataclass in strategy_core.py
3. Add to save logic in ftmo_challenge_analyzer.py if Optuna optimizes it
4. Run scripts/verify_params.py to confirm everything matches
"""

from typing import Dict, Any, List, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETER DEFAULTS - SINGLE SOURCE OF TRUTH
# ═══════════════════════════════════════════════════════════════════════════════
# All parameters used in the trading system are defined here with their defaults.
# These values are used when:
# - A parameter is missing from current_params.json
# - Initializing a new StrategyParams object
# - Validating parameter files

PARAMETER_DEFAULTS: Dict[str, Any] = {
    # ═══════════════════════════════════════════════════════════════════════════
    # CONFLUENCE & ENTRY FILTERS
    # ═══════════════════════════════════════════════════════════════════════════
    'min_confluence': 4,              # Minimum confluence score for entry
    'min_quality_factors': 3,         # Minimum quality factors required
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RISK MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    'risk_per_trade_pct': 0.65,       # 0.65% = $390 per R on $60K account
    'max_open_trades': 3,             # Maximum concurrent trades
    'cooldown_bars': 0,               # Bars between trades per symbol
    'min_rr_ratio': 1.0,              # Minimum R:R ratio required
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STOP LOSS PARAMETERS
    # ═══════════════════════════════════════════════════════════════════════════
    'atr_sl_multiplier': 1.5,         # ATR multiplier for stop loss
    'structure_sl_lookback': 35,      # Bars to look back for structure SL
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TAKE PROFIT R-MULTIPLES (NEW - from Optuna optimization)
    # These define WHERE each TP level is placed in R-multiples
    # ═══════════════════════════════════════════════════════════════════════════
    'tp1_r_multiple': 1.7,            # TP1 at 1.7R profit
    'tp2_r_multiple': 2.7,            # TP2 at 2.7R profit  
    'tp3_r_multiple': 6.0,            # TP3 at 6.0R profit
    
    # Legacy ATR-based TP multipliers (for backward compatibility)
    'atr_tp1_multiplier': 0.6,        # ATR multiplier for TP1
    'atr_tp2_multiplier': 1.2,        # ATR multiplier for TP2
    'atr_tp3_multiplier': 2.0,        # ATR multiplier for TP3
    'atr_tp4_multiplier': 2.5,        # ATR multiplier for TP4
    'atr_tp5_multiplier': 3.5,        # ATR multiplier for TP5
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TAKE PROFIT POSITION SIZING (5-TP SYSTEM - MUST SUM TO 100%!)
    # These define WHAT PERCENTAGE of position closes at each TP level
    # ═══════════════════════════════════════════════════════════════════════════
    'tp1_close_pct': 0.10,            # Close 10% at TP1 (0.6R)
    'tp2_close_pct': 0.10,            # Close 10% at TP2 (1.2R)
    'tp3_close_pct': 0.15,            # Close 15% at TP3 (2.0R)
    'tp4_close_pct': 0.20,            # Close 20% at TP4 (2.5R)
    'tp5_close_pct': 0.45,            # Close 45% at TP5 (3.5R) - ALL remaining
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PARTIAL EXIT & TRAILING STOP
    # ═══════════════════════════════════════════════════════════════════════════
    'partial_exit_at_1r': True,       # Take partial profit at 1R
    'partial_exit_pct': 0.75,         # Percentage to close at 1R (75%)
    'trail_activation_r': 0.65,       # Activate trailing stop after this R
    'atr_trail_multiplier': 1.6,      # ATR multiplier for trail distance
    'use_atr_trailing': True,         # Enable ATR trailing on runner
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIBONACCI PARAMETERS
    # ═══════════════════════════════════════════════════════════════════════════
    'fib_low': 0.382,                 # Lower Fib zone
    'fib_high': 0.886,                # Upper Fib zone
    'fib_range_target': 0.786,        # Fib level for range mode entries
    'fib_zone_type': 'golden_only',   # Options: 'golden_only', 'extended', 'full'
    'use_fib_filter': False,          # Enable Fib zone filter
    'use_fib_0786_only': False,       # Require 0.786 zone only
    
    # ═══════════════════════════════════════════════════════════════════════════
    # REGIME DETECTION (ADX-based)
    # ═══════════════════════════════════════════════════════════════════════════
    'adx_trend_threshold': 20.0,      # ADX >= this = Trend Mode
    'adx_range_threshold': 13.0,      # ADX < this = Range Mode
    'trend_min_confluence': 6,        # Min confluence for trend mode
    'range_min_confluence': 3,        # Min confluence for range mode
    'use_adx_regime_filter': False,   # Enable ADX-based regime filtering
    'use_adx_slope_rising': False,    # Allow entries on rising ADX
    
    # ═══════════════════════════════════════════════════════════════════════════
    # VOLATILITY PARAMETERS
    # ═══════════════════════════════════════════════════════════════════════════
    'atr_min_percentile': 42.0,       # Minimum ATR percentile
    'atr_volatility_ratio': 0.9,      # Current ATR / ATR(50) ratio for range mode
    'atr_vol_ratio_range': 0.9,       # Alias for atr_volatility_ratio
    'december_atr_multiplier': 1.7,   # Stricter ATR in December
    'volatile_asset_boost': 1.35,     # Scoring boost for high-ATR assets
    'use_volatility_sizing_boost': False,  # Increase risk in high ATR periods
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FILTER TOGGLES (all disabled for baseline)
    # ═══════════════════════════════════════════════════════════════════════════
    'use_htf_filter': False,          # Higher timeframe filter
    'use_structure_filter': False,    # Market structure filter
    'use_confirmation_filter': False, # Entry confirmation filter
    'use_displacement_filter': False, # Strong candle displacement
    'use_candle_rejection': False,    # Pinbar/engulfing filter
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ADVANCED FILTERS (disabled for baseline)
    # ═══════════════════════════════════════════════════════════════════════════
    'use_atr_regime_filter': False,   # ATR regime filter
    'use_zscore_filter': False,       # Z-score filter
    'zscore_threshold': 1.5,          # Z-score threshold
    'use_pattern_filter': False,      # Pattern recognition filter
    'use_momentum_filter': False,     # Momentum filter
    'momentum_lookback': 10,          # Momentum lookback period
    'use_mean_reversion': False,      # Mean reversion filter
    'use_mitigated_sr': False,        # Mitigated S/R zones
    'use_structural_framework': False, # Structural framework
    'use_market_structure_bos_only': False,  # BOS only mode
    'sr_proximity_pct': 0.02,         # S/R proximity percentage
    'displacement_atr_mult': 1.5,     # Displacement ATR multiplier
    'candle_pattern_strictness': 'moderate',  # Pattern strictness level
    'ml_min_prob': 0.6,               # ML minimum probability
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HTF ALIGNMENT
    # ═══════════════════════════════════════════════════════════════════════════
    'require_htf_alignment': False,   # Require HTF trend alignment
    'require_confirmation_for_active': False,  # Require confirmation for active
    'require_rr_for_active': False,   # Require R:R for active signals
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SESSION FILTER
    # ═══════════════════════════════════════════════════════════════════════════
    'use_session_filter': True,       # Only trade London/NY hours
    'session_start_utc': 8,           # Session start (London open)
    'session_end_utc': 22,            # Session end (NY close)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # GRADUATED RISK MANAGEMENT (for FTMO drawdown protection)
    # ═══════════════════════════════════════════════════════════════════════════
    'use_graduated_risk': True,       # Enable graduated risk
    'tier1_dd_pct': 2.0,              # Reduce risk at this daily DD%
    'tier1_risk_factor': 0.67,        # Risk multiplier (0.6% -> 0.4%)
    'tier2_dd_pct': 3.5,              # Cancel pending at this daily DD%
    'tier3_dd_pct': 4.5,              # Emergency close at this daily DD%
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FTMO COMPLIANCE PARAMETERS (NEW)
    # These are used by the optimizer and compliance tracker
    # ═══════════════════════════════════════════════════════════════════════════
    'daily_loss_halt_pct': 4.1,       # Halt trading at this daily DD%
    'max_total_dd_warning': 7.9,      # Warning at this total DD%
    'consecutive_loss_halt': 9,       # Halt after this many consecutive losses
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_default(param_name: str) -> Any:
    """Get default value for a parameter."""
    if param_name not in PARAMETER_DEFAULTS:
        raise KeyError(f"Unknown parameter: {param_name}. "
                      f"Add it to params/defaults.py PARAMETER_DEFAULTS dict.")
    return PARAMETER_DEFAULTS[param_name]


def get_all_defaults() -> Dict[str, Any]:
    """Get copy of all defaults."""
    return PARAMETER_DEFAULTS.copy()


def get_boolean_params() -> Dict[str, bool]:
    """Get all boolean parameters."""
    return {k: v for k, v in PARAMETER_DEFAULTS.items() if isinstance(v, bool)}


def get_numeric_params() -> Dict[str, float]:
    """Get all numeric parameters (int or float)."""
    return {k: v for k, v in PARAMETER_DEFAULTS.items() 
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def validate_params(params: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Validate parameters against defaults.
    
    Args:
        params: Dictionary of parameters to validate
        
    Returns:
        Tuple of (is_valid, missing_params, extra_params)
    """
    expected = set(PARAMETER_DEFAULTS.keys())
    actual = set(params.keys())
    
    missing = expected - actual
    extra = actual - expected
    
    # Filter out known non-parameter keys
    metadata_keys = {'optimization_mode', 'timestamp', 'best_score', 
                     'generated_at', 'generated_by', 'version', 'parameters'}
    extra = extra - metadata_keys
    
    is_valid = len(missing) == 0
    
    return is_valid, sorted(list(missing)), sorted(list(extra))


def merge_with_defaults(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge provided parameters with defaults.
    
    Parameters from input override defaults.
    All missing parameters get default values.
    
    Args:
        params: Dictionary of parameters (may be incomplete)
        
    Returns:
        Complete dictionary with all parameters
    """
    result = PARAMETER_DEFAULTS.copy()
    
    for key, value in params.items():
        if key in result:
            result[key] = value
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print("PARAMETER DEFAULTS - SINGLE SOURCE OF TRUTH")
    print("=" * 70)
    
    print(f"\n📊 Total parameters: {len(PARAMETER_DEFAULTS)}")
    
    bool_params = get_boolean_params()
    numeric_params = get_numeric_params()
    
    print(f"   Boolean parameters: {len(bool_params)}")
    print(f"   Numeric parameters: {len(numeric_params)}")
    
    print(f"\n🔘 Boolean parameters:")
    for k, v in sorted(bool_params.items()):
        status = "ON" if v else "OFF"
        print(f"   {k}: {status}")
    
    print(f"\n📋 All parameters:")
    for key, value in sorted(PARAMETER_DEFAULTS.items()):
        if isinstance(value, float):
            print(f"   {key}: {value:.4f}")
        else:
            print(f"   {key}: {value}")
