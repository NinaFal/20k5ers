#!/usr/bin/env python3
"""
Validate that all components use the same parameters.

Checks:
1. strategy_core.py uses tp_r_multiple (not atr_tp_multiplier)
2. main_live_bot.py loads current_params.json
3. No hardcoded TP values in ftmo_config.py
4. partial_exit_at_1r is implemented everywhere
"""

import json
import re
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_strategy_core():
    """Check strategy_core.py alignment."""
    print("\n📋 CHECKING: strategy_core.py")
    
    with open("strategy_core.py") as f:
        content = f.read()
    
    issues = []
    
    # Check that tp_r_multiple is used in TP calculations
    if "params.tp1_r_multiple" in content and "params.tp2_r_multiple" in content:
        print("   ✅ Uses params.tp_r_multiple for TP calculations")
    else:
        issues.append("❌ Not using params.tp_r_multiple for TP calculations")
    
    # Check for old atr_tp_multiplier usage in calculations (not declarations)
    calc_lines = [line for line in content.split('\n') 
                  if 'entry +' in line or 'entry -' in line]
    old_usage = [line for line in calc_lines if 'atr_tp' in line and 'params.' in line]
    if old_usage:
        issues.append(f"❌ Still uses atr_tp_multiplier in calculations: {len(old_usage)} lines")
    else:
        print("   ✅ No atr_tp_multiplier in calculations")
    
    # Check for partial_exit params
    if "partial_exit_at_1r" in content and "partial_exit_pct" in content:
        print("   ✅ partial_exit_at_1r parameter defined")
    else:
        issues.append("❌ partial_exit_at_1r parameter NOT defined")
    
    return issues


def check_main_live_bot():
    """Check main_live_bot.py alignment."""
    print("\n📋 CHECKING: main_live_bot.py")
    
    with open("main_live_bot.py") as f:
        content = f.read()
    
    issues = []
    
    # Check if loads current_params.json
    if "current_params.json" in content or "load_best_params_from_file" in content:
        print("   ✅ Loads current_params.json")
    else:
        issues.append("❌ Does NOT load current_params.json")
    
    # Check that it uses self.params for TP calculations
    if "self.params.tp1_r_multiple" in content:
        print("   ✅ Uses self.params.tp_r_multiple for TPs")
    else:
        issues.append("❌ Not using self.params.tp_r_multiple")
    
    # Check for FIVEERS_CONFIG.tp usage (should be gone)
    if "FIVEERS_CONFIG.tp1_r_multiple" in content or "FIVEERS_CONFIG.tp2_r_multiple" in content:
        issues.append("❌ Still uses FIVEERS_CONFIG for TP levels")
    else:
        print("   ✅ No FIVEERS_CONFIG.tp_r_multiple usage")
    
    # Check for self.params.tp_close_pct usage
    if "self.params.tp1_close_pct" in content:
        print("   ✅ Uses self.params.tp_close_pct")
    else:
        issues.append("❌ Not using self.params.tp_close_pct")
    
    return issues


def check_ftmo_config():
    """Check ftmo_config.py for proper deprecation markers."""
    print("\n📋 CHECKING: ftmo_config.py")
    
    if not Path("ftmo_config.py").exists():
        print("   ⚠️ File not found (may be OK if removed)")
        return []
    
    with open("ftmo_config.py") as f:
        content = f.read()
    
    issues = []
    
    # Check that TP levels are marked as deprecated
    if "DEPRECATED" in content and "current_params.json" in content:
        print("   ✅ TP levels marked as DEPRECATED")
    else:
        issues.append("⚠️ TP levels should be marked as DEPRECATED")
    
    return issues


def check_current_params():
    """Verify current_params.json exists and has required fields."""
    print("\n📋 CHECKING: params/current_params.json")
    
    params_file = Path("params/current_params.json")
    if not params_file.exists():
        return ["❌ params/current_params.json NOT FOUND"]
    
    with open(params_file) as f:
        data = json.load(f)
    
    # Handle nested structure
    if "parameters" in data:
        if isinstance(data["parameters"], dict) and "parameters" in data["parameters"]:
            params = data["parameters"]["parameters"]  # Double nested
        else:
            params = data["parameters"]
    else:
        params = data
    
    required = [
        "tp1_r_multiple", "tp2_r_multiple", "tp3_r_multiple",
        "tp1_close_pct", "tp2_close_pct", "tp3_close_pct",
        "partial_exit_at_1r", "partial_exit_pct",
        "trail_activation_r",
    ]
    
    issues = []
    for param in required:
        if param in params:
            print(f"   ✅ {param}: {params[param]}")
        else:
            issues.append(f"❌ Missing: {param}")
    
    return issues


def check_h1_simulator():
    """Check H1 simulator alignment."""
    print("\n📋 CHECKING: tradr/backtest/h1_trade_simulator.py")
    
    sim_file = Path("tradr/backtest/h1_trade_simulator.py")
    if not sim_file.exists():
        print("   ⚠️ H1 simulator not found (may not be needed)")
        return []
    
    with open(sim_file) as f:
        content = f.read()
    
    issues = []
    
    # Check TP level constants
    if "TP1_R = 0.6" in content:
        issues.append("⚠️ H1 simulator uses old TP levels (0.6R) - update to match current_params!")
    else:
        print("   ✅ TP levels appear correct")
    
    return issues


def main():
    print("═" * 70)
    print("PROJECT ALIGNMENT VALIDATION")
    print("═" * 70)
    
    all_issues = []
    
    all_issues.extend(check_current_params())
    all_issues.extend(check_strategy_core())
    all_issues.extend(check_main_live_bot())
    all_issues.extend(check_ftmo_config())
    all_issues.extend(check_h1_simulator())
    
    print("\n" + "═" * 70)
    
    # Filter out warnings (⚠️) from critical issues (❌)
    critical = [i for i in all_issues if i.startswith("❌")]
    warnings = [i for i in all_issues if i.startswith("⚠️")]
    
    if critical:
        print("❌ CRITICAL ISSUES FOUND:")
        for issue in critical:
            print(f"   {issue}")
    
    if warnings:
        print("\n⚠️ WARNINGS:")
        for warning in warnings:
            print(f"   {warning}")
    
    if not critical and not warnings:
        print("✅ ALL COMPONENTS ALIGNED!")
        
    if not critical:
        print("\n📊 CURRENT CONFIGURATION:")
        
        params_file = Path("params/current_params.json")
        if params_file.exists():
            with open(params_file) as f:
                data = json.load(f)
            
            if "parameters" in data:
                if isinstance(data["parameters"], dict) and "parameters" in data["parameters"]:
                    params = data["parameters"]["parameters"]
                else:
                    params = data["parameters"]
            else:
                params = data
            
            print(f"\n   TP Levels (from current_params.json):")
            print(f"   ├── TP1: {params.get('tp1_r_multiple', 'N/A')}R")
            print(f"   ├── TP2: {params.get('tp2_r_multiple', 'N/A')}R")
            print(f"   └── TP3: {params.get('tp3_r_multiple', 'N/A')}R")
            
            print(f"\n   Close Percentages:")
            print(f"   ├── TP1: {params.get('tp1_close_pct', 'N/A')}")
            print(f"   ├── TP2: {params.get('tp2_close_pct', 'N/A')}")
            print(f"   └── TP3: {params.get('tp3_close_pct', 'N/A')}")
            
            print(f"\n   Partial Exit at 1R:")
            print(f"   ├── Enabled: {params.get('partial_exit_at_1r', 'N/A')}")
            print(f"   └── Percentage: {params.get('partial_exit_pct', 'N/A')}")
            
            print(f"\n   Trail Activation: {params.get('trail_activation_r', 'N/A')}R")
        
        return 0
    else:
        print("\n⚠️ Fix critical issues before running live!")
        return 1


if __name__ == "__main__":
    exit(main())
