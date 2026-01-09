#!/usr/bin/env python3
"""
Extract exit strategy parameters from validation/optimization results.

Usage:
    python scripts/extract_exit_params.py [params_file]
    
Examples:
    python scripts/extract_exit_params.py  # Uses default current_params.json
    python scripts/extract_exit_params.py ftmo_analysis_output/VALIDATE/history/val_2023_2025_003/best_params.json
"""

import json
import sys
from pathlib import Path

# Default file
DEFAULT_PARAMS = "params/current_params.json"


def extract_exit_params(params_file: str) -> dict:
    """
    Extract exit-strategy-relevant parameters from a params file.
    
    Args:
        params_file: Path to JSON file with parameters
        
    Returns:
        Dictionary with exit strategy parameters
    """
    path = Path(params_file)
    if not path.exists():
        raise FileNotFoundError(f"Parameters file not found: {params_file}")
    
    with open(path) as f:
        data = json.load(f)
    
    # Handle nested structure (VALIDATE mode wraps params)
    if "parameters" in data and isinstance(data["parameters"], dict):
        inner = data["parameters"]
        if "parameters" in inner and isinstance(inner["parameters"], dict):
            # Double-nested (VALIDATE mode)
            params = inner["parameters"]
        else:
            params = inner
    else:
        params = data
    
    # Extract exit-related parameters
    exit_params = {
        "# TP R-MULTIPLES (metadata/logging only - not used in backtest pricing)": "",
        "tp1_r_multiple": params.get("tp1_r_multiple", 1.7),
        "tp2_r_multiple": params.get("tp2_r_multiple", 2.7),
        "tp3_r_multiple": params.get("tp3_r_multiple", 6.0),
        
        "# TP ATR MULTIPLIERS (actually used for TP price calculation)": "",
        "atr_tp1_multiplier": params.get("atr_tp1_multiplier", 0.6),
        "atr_tp2_multiplier": params.get("atr_tp2_multiplier", 1.2),
        "atr_tp3_multiplier": params.get("atr_tp3_multiplier", 2.0),
        
        "# TP CLOSE PERCENTAGES (position sizing per TP level)": "",
        "tp1_close_pct": params.get("tp1_close_pct", 0.35),
        "tp2_close_pct": params.get("tp2_close_pct", 0.30),
        "tp3_close_pct": params.get("tp3_close_pct", 0.35),
        
        "# TRAILING STOP": "",
        "trail_activation_r": params.get("trail_activation_r", 0.65),
        "atr_trail_multiplier": params.get("atr_trail_multiplier", 1.6),
        
        "# PARTIAL EXIT (not implemented in backtest)": "",
        "partial_exit_at_1r": params.get("partial_exit_at_1r", True),
        "partial_exit_pct": params.get("partial_exit_pct", 0.75),
        
        "# STOP LOSS": "",
        "atr_sl_multiplier": params.get("atr_sl_multiplier", 1.5),
        "structure_sl_lookback": params.get("structure_sl_lookback", 35),
    }
    
    return exit_params


def validate_close_pcts(params: dict) -> tuple[bool, float]:
    """
    Check if close percentages sum to reasonable value.
    
    Returns:
        (is_valid, total_sum)
    """
    close_keys = ["tp1_close_pct", "tp2_close_pct", "tp3_close_pct"]
    total = sum(params.get(k, 0) for k in close_keys)
    # Should be close to 1.0 but can be slightly off
    is_valid = 0.8 <= total <= 1.2
    return is_valid, total


def main():
    params_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PARAMS
    
    print("=" * 70)
    print("EXIT STRATEGY PARAMETERS EXTRACTION")
    print("=" * 70)
    print(f"\n📁 Source: {params_file}\n")
    
    try:
        exit_params = extract_exit_params(params_file)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    
    print("📊 EXIT STRATEGY PARAMETERS:")
    print("-" * 50)
    
    for key, value in exit_params.items():
        if key.startswith("#"):
            print(f"\n{key}")
        elif isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        elif isinstance(value, bool):
            print(f"  {key}: {'ON' if value else 'OFF'}")
        else:
            print(f"  {key}: {value}")
    
    # Validate close percentages
    is_valid, total = validate_close_pcts(exit_params)
    print(f"\n📋 VALIDATION:")
    print(f"  Close % total: {total:.2f} {'✅' if is_valid else '⚠️'}")
    
    if not is_valid:
        print("  ⚠️  Warning: Close percentages may not sum to expected 1.0")
    
    # Calculate example RR for full TP3 exit (3-TP simplified strategy)
    tp_close = [
        exit_params["tp1_close_pct"],
        exit_params["tp2_close_pct"],
        exit_params["tp3_close_pct"],
    ]
    tp_r = [
        exit_params["atr_tp1_multiplier"],
        exit_params["atr_tp2_multiplier"],
        exit_params.get("atr_tp3_multiplier", 2.0),
    ]
    
    full_rr = sum(c * r for c, r in zip(tp_close, tp_r))
    print(f"\n📈 EXAMPLE CALCULATIONS:")
    print(f"  Full TP3 exit RR: {full_rr:.3f}R")
    print(f"  (assuming all TP levels hit at ATR multiplier values)")
    
    # Export as JSON for H1 backtester
    export_file = Path(params_file).stem + "_exit_params.json"
    export_path = Path("params") / export_file
    
    # Clean export (remove comment keys)
    clean_export = {k: v for k, v in exit_params.items() if not k.startswith("#")}
    
    with open(export_path, "w") as f:
        json.dump(clean_export, f, indent=2)
    
    print(f"\n💾 Exported to: {export_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
