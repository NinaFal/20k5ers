#!/usr/bin/env python3
"""
Parameter Audit Tool - STAP 4.

Audits all parameters across the codebase to identify:
1. Parameters suggested by Optuna
2. Parameters defined in StrategyParams dataclass
3. Parameters in current_params.json
4. Parameters used in main_live_bot.py
5. Mismatches and missing parameters

This audit identifies critical bugs where:
- Parameters optimized by Optuna aren't being saved
- Parameters saved aren't being loaded by live bot
- Default values differ between files
"""

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Any, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ParameterInfo:
    """Information about a parameter."""
    name: str
    source: str
    param_type: Optional[str] = None
    default_value: Optional[Any] = None
    is_boolean: bool = False
    line_number: Optional[int] = None


def extract_optuna_params(filepath: Path) -> List[ParameterInfo]:
    """Extract all trial.suggest_* calls from optimizer."""
    params = []
    
    content = filepath.read_text()
    lines = content.split('\n')
    
    # Pattern for trial.suggest_* calls
    patterns = [
        (r"trial\.suggest_float\(['\"](\w+)['\"]", "float"),
        (r"trial\.suggest_int\(['\"](\w+)['\"]", "int"),
        (r"trial\.suggest_categorical\(['\"](\w+)['\"]", "categorical"),
        (r"trial\.suggest_uniform\(['\"](\w+)['\"]", "float"),
        (r"trial\.suggest_loguniform\(['\"](\w+)['\"]", "float"),
    ]
    
    for line_num, line in enumerate(lines, 1):
        for pattern, param_type in patterns:
            matches = re.findall(pattern, line)
            for match in matches:
                is_bool = 'True' in line and 'False' in line  # categorical bool
                params.append(ParameterInfo(
                    name=match,
                    source='optuna',
                    param_type=param_type,
                    is_boolean=is_bool,
                    line_number=line_num,
                ))
    
    return params


def extract_dataclass_params(filepath: Path) -> List[ParameterInfo]:
    """Extract parameters from StrategyParams dataclass."""
    params = []
    
    content = filepath.read_text()
    
    # Find the StrategyParams class
    class_match = re.search(r'class StrategyParams:.*?(?=\nclass |\n@dataclass|\Z)', content, re.DOTALL)
    if not class_match:
        return params
    
    class_content = class_match.group(0)
    
    # Pattern for dataclass fields: name: type = default
    field_pattern = re.compile(
        r'^\s+(\w+):\s+(\w+)\s*=\s*(.+?)(?:\s*#.*)?$',
        re.MULTILINE
    )
    
    for match in field_pattern.finditer(class_content):
        name = match.group(1)
        param_type = match.group(2)
        default_str = match.group(3).strip()
        
        # Parse default value
        try:
            if default_str == 'True':
                default_value = True
            elif default_str == 'False':
                default_value = False
            elif default_str.startswith("'") or default_str.startswith('"'):
                default_value = default_str.strip("'\"")
            elif '.' in default_str:
                default_value = float(default_str)
            else:
                default_value = int(default_str)
        except ValueError:
            default_value = default_str
        
        params.append(ParameterInfo(
            name=name,
            source='dataclass',
            param_type=param_type,
            default_value=default_value,
            is_boolean=isinstance(default_value, bool),
        ))
    
    return params


def extract_json_params(filepath: Path) -> List[ParameterInfo]:
    """Extract parameters from JSON file."""
    if not filepath.exists():
        return []
    
    data = json.loads(filepath.read_text())
    
    # Handle nested 'parameters' key
    params_dict = data.get('parameters', data)
    
    params = []
    for key, value in params_dict.items():
        if key in ['optimization_mode', 'timestamp', 'best_score', 'generated_at', 'generated_by', 'version']:
            continue  # Skip metadata
        
        params.append(ParameterInfo(
            name=key,
            source='json',
            param_type=type(value).__name__,
            default_value=value,
            is_boolean=isinstance(value, bool),
        ))
    
    return params


def extract_code_usage(filepath: Path) -> List[ParameterInfo]:
    """Extract how parameters are used (params.get, params[])."""
    params = []
    
    content = filepath.read_text()
    lines = content.split('\n')
    
    # Patterns for parameter access
    patterns = [
        r"(?:self\.)?params\.get\(['\"](\w+)['\"](?:,\s*([^)]+))?\)",
        r"(?:self\.)?params\[['\"](\w+)['\"]\]",
        r"data\.get\(['\"](\w+)['\"](?:,\s*([^)]+))?\)",
        r"params_dict\.get\(['\"](\w+)['\"](?:,\s*([^)]+))?\)",
    ]
    
    seen = set()
    for line_num, line in enumerate(lines, 1):
        for pattern in patterns:
            matches = re.findall(pattern, line)
            for match in matches:
                if isinstance(match, tuple):
                    name = match[0]
                    default = match[1] if len(match) > 1 and match[1] else None
                else:
                    name = match
                    default = None
                
                if name not in seen:
                    seen.add(name)
                    params.append(ParameterInfo(
                        name=name,
                        source=filepath.name,
                        default_value=default.strip() if default else None,
                        line_number=line_num,
                    ))
    
    return params


def main():
    print("=" * 70)
    print("PARAMETER AUDIT - STAP 4")
    print("=" * 70)
    
    # File paths
    ftmo_analyzer = PROJECT_ROOT / 'ftmo_challenge_analyzer.py'
    strategy_core = PROJECT_ROOT / 'strategy_core.py'
    main_live_bot = PROJECT_ROOT / 'main_live_bot.py'
    current_params = PROJECT_ROOT / 'params' / 'current_params.json'
    params_loader = PROJECT_ROOT / 'params' / 'params_loader.py'
    
    # Extract from all sources
    print("\n📊 Extracting parameters from all sources...")
    
    optuna_params = extract_optuna_params(ftmo_analyzer)
    print(f"   Optuna (ftmo_challenge_analyzer.py): {len(optuna_params)} params")
    
    dataclass_params = extract_dataclass_params(strategy_core)
    print(f"   StrategyParams dataclass: {len(dataclass_params)} params")
    
    json_params = extract_json_params(current_params)
    print(f"   current_params.json: {len(json_params)} params")
    
    live_bot_usage = extract_code_usage(main_live_bot)
    print(f"   main_live_bot.py usage: {len(live_bot_usage)} params")
    
    loader_usage = extract_code_usage(params_loader)
    print(f"   params_loader.py usage: {len(loader_usage)} params")
    
    # Create name sets
    optuna_names = {p.name for p in optuna_params}
    dataclass_names = {p.name for p in dataclass_params}
    json_names = {p.name for p in json_params}
    usage_names = {p.name for p in live_bot_usage} | {p.name for p in loader_usage}
    
    all_params = optuna_names | dataclass_names | json_names | usage_names
    
    print(f"\n   Total unique parameters: {len(all_params)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CRITICAL ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    
    print(f"\n{'='*70}")
    print("🔍 CRITICAL ANALYSIS")
    print("="*70)
    
    # 1. Params optimized by Optuna but NOT in StrategyParams dataclass
    optuna_not_in_dataclass = optuna_names - dataclass_names
    if optuna_not_in_dataclass:
        print(f"\n⚠️ OPTIMIZED BUT NOT IN DATACLASS ({len(optuna_not_in_dataclass)}):")
        print("   These params are optimized but can't be used by StrategyParams!")
        for p in sorted(optuna_not_in_dataclass):
            print(f"      - {p}")
    
    # 2. Params in StrategyParams but NOT in Optuna
    dataclass_not_in_optuna = dataclass_names - optuna_names - {'min_rr_ratio', 'cooldown_bars', 'max_open_trades'}
    # Filter out params that don't need optimization
    dataclass_not_in_optuna = {p for p in dataclass_not_in_optuna if not p.startswith('atr_tp')}
    if dataclass_not_in_optuna:
        print(f"\n📋 IN DATACLASS BUT NOT OPTIMIZED ({len(dataclass_not_in_optuna)}):")
        print("   These use fixed defaults (may or may not need optimization):")
        for p in sorted(dataclass_not_in_optuna):
            dc_param = next((x for x in dataclass_params if x.name == p), None)
            default = dc_param.default_value if dc_param else 'N/A'
            print(f"      - {p}: {default}")
    
    # 3. Params in JSON but NOT matching dataclass
    json_not_in_dataclass = json_names - dataclass_names
    if json_not_in_dataclass:
        print(f"\n❌ IN JSON BUT NOT IN DATACLASS ({len(json_not_in_dataclass)}):")
        print("   CRITICAL: These params are saved but can't be loaded!")
        for p in sorted(json_not_in_dataclass):
            json_param = next((x for x in json_params if x.name == p), None)
            value = json_param.default_value if json_param else 'N/A'
            print(f"      - {p}: {value}")
    
    # 4. Boolean parameters check
    print(f"\n{'='*70}")
    print("🔘 BOOLEAN PARAMETERS CHECK")
    print("="*70)
    
    optuna_bools = [p for p in optuna_params if p.is_boolean]
    json_bools = [p for p in json_params if p.is_boolean]
    dataclass_bools = [p for p in dataclass_params if p.is_boolean]
    
    print(f"\n   In Optuna: {len(optuna_bools)}")
    print(f"   In JSON: {len(json_bools)}")
    print(f"   In Dataclass: {len(dataclass_bools)}")
    
    # Compare boolean values
    print(f"\n   Boolean values comparison:")
    all_bool_names = {p.name for p in optuna_bools} | {p.name for p in json_bools} | {p.name for p in dataclass_bools}
    
    for name in sorted(all_bool_names):
        json_val = next((p.default_value for p in json_params if p.name == name and p.is_boolean), None)
        dc_val = next((p.default_value for p in dataclass_params if p.name == name and p.is_boolean), None)
        in_optuna = name in {p.name for p in optuna_bools}
        
        # Check for mismatches
        mismatch = ""
        if json_val is not None and dc_val is not None and json_val != dc_val:
            mismatch = " ⚠️ MISMATCH!"
        
        json_str = f"JSON={json_val}" if json_val is not None else "JSON=❌"
        dc_str = f"DC={dc_val}" if dc_val is not None else "DC=❌"
        opt_str = "OPT=✅" if in_optuna else "OPT=❌"
        
        print(f"      {name}: {json_str}, {dc_str}, {opt_str}{mismatch}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FULL PARAMETER MATRIX
    # ═══════════════════════════════════════════════════════════════════════════
    
    print(f"\n{'='*70}")
    print("📋 FULL PARAMETER MATRIX")
    print("="*70)
    print(f"\n{'Parameter':<35} {'Optuna':<8} {'DataC':<8} {'JSON':<8} {'Used':<8}")
    print("-" * 70)
    
    for param in sorted(all_params):
        in_optuna = '✅' if param in optuna_names else '❌'
        in_dc = '✅' if param in dataclass_names else '❌'
        in_json = '✅' if param in json_names else '❌'
        in_usage = '✅' if param in usage_names else '➖'
        print(f"{param:<35} {in_optuna:<8} {in_dc:<8} {in_json:<8} {in_usage:<8}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SAVE DETAILED REPORT
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Create detailed dataclass defaults dict
    dataclass_defaults = {p.name: p.default_value for p in dataclass_params}
    json_values = {p.name: p.default_value for p in json_params}
    
    report = {
        'summary': {
            'optuna_params': len(optuna_names),
            'dataclass_params': len(dataclass_names),
            'json_params': len(json_names),
            'total_unique': len(all_params),
        },
        'optuna_params': sorted(list(optuna_names)),
        'dataclass_params': sorted(list(dataclass_names)),
        'json_params': sorted(list(json_names)),
        'issues': {
            'optuna_not_in_dataclass': sorted(list(optuna_not_in_dataclass)),
            'json_not_in_dataclass': sorted(list(json_not_in_dataclass)),
        },
        'dataclass_defaults': dataclass_defaults,
        'json_values': json_values,
        'boolean_params': sorted([p.name for p in dataclass_bools]),
    }
    
    output_file = PROJECT_ROOT / 'analysis' / 'parameter_audit.json'
    output_file.write_text(json.dumps(report, indent=2, default=str))
    
    print(f"\n{'='*70}")
    print(f"✅ Detailed report saved to: {output_file}")
    print("="*70)
    
    # Return exit code based on issues
    has_issues = len(optuna_not_in_dataclass) > 0 or len(json_not_in_dataclass) > 0
    return 1 if has_issues else 0


if __name__ == '__main__':
    sys.exit(main())
