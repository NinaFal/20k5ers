#!/usr/bin/env python3
"""
Parameter Verification Script - 5-TP System Compliant

Verifies parameter consistency between optimizer and live bot.
Ensures current_params.json has all required parameters for the 5-TP system.

Usage:
    python scripts/verify_params.py

Exit codes:
  0 - All checks passed
  1 - Some checks failed
"""

import json
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from params.params_loader import load_strategy_params, load_params_dict
from params.defaults import PARAMETER_DEFAULTS


def verify_params() -> bool:
    """
    Verify that current_params.json has all required parameters.
    
    Returns:
        True if all required parameters are present, False otherwise.
    """
    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    
    if not params_file.exists():
        print("❌ ERROR: params/current_params.json does not exist!")
        print("   Run: python scripts/select_run.py <run_name>")
        return False
    
    with open(params_file, 'r') as f:
        raw = json.load(f)
    
    # Extract parameters (handle nested structure)
    if "parameters" in raw:
        params = raw["parameters"]
    else:
        params = {k: v for k, v in raw.items() if not k.startswith("_")}
    
    print("=" * 70)
    print("PARAMETER CONSISTENCY CHECK - 5-TP SYSTEM")
    print("=" * 70)
    print(f"File: {params_file}")
    print()
    
    # Check for missing parameters
    missing = set(PARAMETER_DEFAULTS.keys()) - set(params.keys())
    extra = set(params.keys()) - set(PARAMETER_DEFAULTS.keys())
    
    if missing:
        print(f"⚠️ MISSING PARAMETERS ({len(missing)}):")
        for p in sorted(missing):
            print(f"   - {p}: using default = {PARAMETER_DEFAULTS[p]}")
        print()
    
    if extra:
        print(f"ℹ️ EXTRA PARAMETERS ({len(extra)}):")
        for p in sorted(extra):
            print(f"   - {p}: {params[p]}")
        print()
    
    # Load merged params
    merged = load_strategy_params()
    
    print("KEY PARAMETERS (from current_params.json + defaults):")
    print("-" * 70)
    
    # 5-TP system - Use atr_tp*_multiplier naming
    print("\n5-TP SYSTEM:")
    print(f"  TP1: {merged.atr_tp1_multiplier}R -> close {merged.tp1_close_pct*100:.0f}%")
    print(f"  TP2: {merged.atr_tp2_multiplier}R -> close {merged.tp2_close_pct*100:.0f}%")
    print(f"  TP3: {merged.atr_tp3_multiplier}R -> close {merged.tp3_close_pct*100:.0f}%")
    print(f"  TP4: {merged.atr_tp4_multiplier}R -> close {merged.tp4_close_pct*100:.0f}%")
    print(f"  TP5: {merged.atr_tp5_multiplier}R -> close {merged.tp5_close_pct*100:.0f}%")
    
    # Risk
    print("\nRISK SETTINGS:")
    print(f"  Risk per trade: {merged.risk_per_trade_pct}%")
    print(f"  Trail activation: {merged.trail_activation_r}R")
    
    # Confluence
    print("\nCONFLUENCE:")
    print(f"  Min confluence: {merged.min_confluence}")
    print(f"  Min quality factors: {merged.min_quality_factors}")
    
    print()
    print("=" * 70)
    
    # Validation check
    total_close_pct = (merged.tp1_close_pct + merged.tp2_close_pct + 
                       merged.tp3_close_pct + merged.tp4_close_pct + 
                       merged.tp5_close_pct)
    
    errors = []
    
    if abs(total_close_pct - 1.0) > 0.01:
        errors.append(f"TP close percentages sum to {total_close_pct*100:.0f}%, not 100%!")
        print(f"⚠️ WARNING: {errors[-1]}")
    else:
        print("✅ TP close percentages sum to 100%")
    
    # Check TP ordering
    tp_levels = [
        merged.atr_tp1_multiplier,
        merged.atr_tp2_multiplier,
        merged.atr_tp3_multiplier,
        merged.atr_tp4_multiplier,
        merged.atr_tp5_multiplier,
    ]
    
    for i in range(1, len(tp_levels)):
        if tp_levels[i] <= tp_levels[i-1]:
            errors.append(f"TP{i+1} ({tp_levels[i]}R) is not greater than TP{i} ({tp_levels[i-1]}R)")
            print(f"⚠️ WARNING: {errors[-1]}")
    
    if not errors or all('TP' in e for e in errors):
        if all(tp_levels[i] > tp_levels[i-1] for i in range(1, len(tp_levels))):
            print("✅ TP levels properly ordered")
    
    if not missing:
        print("✅ All required parameters present")
    
    # Summary
    print()
    print("=" * 70)
    if not missing and not errors:
        print("✅ PARAMETER CHECK PASSED - Ready for live trading!")
    else:
        print("⚠️ PARAMETER CHECK WARNING - Review issues above")
    print("=" * 70)
    
    return len(missing) == 0 and len(errors) == 0


def main():
    """Main entry point."""
    print()
    success = verify_params()
    print()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
