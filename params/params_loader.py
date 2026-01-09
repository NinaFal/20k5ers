"""
Parameter Loader - Single Source of Truth for Strategy Parameters.

This module loads optimized parameters from params/current_params.json.
All trading components (live bot, backtests) must use this loader.

Usage:
    from params.params_loader import load_strategy_params, get_transaction_costs
    
    params = load_strategy_params()  # Returns StrategyParams object
    costs = get_transaction_costs("EURUSD")  # Returns spread, slippage, commission
"""

import json
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
from dataclasses import dataclass


PARAMS_FILE = Path(__file__).parent / "current_params.json"


class ParamsNotFoundError(Exception):
    """Raised when params file doesn't exist. Run optimizer first."""
    pass


def load_params_dict() -> Dict[str, Any]:
    """
    Load raw parameters dictionary from JSON file.
    
    Returns:
        Dict with all parameters
        
    Raises:
        ParamsNotFoundError: If params file doesn't exist
    """
    if not PARAMS_FILE.exists():
        raise ParamsNotFoundError(
            f"Parameters file not found: {PARAMS_FILE}\n"
            "Run the optimizer first: python ftmo_challenge_analyzer.py"
        )
    
    with open(PARAMS_FILE, 'r') as f:
        return json.load(f)


def load_strategy_params():
    """
    Load optimized strategy parameters.
    
    Uses params/defaults.py as SINGLE SOURCE OF TRUTH for default values.
    Loads from JSON and merges with defaults.
    
    Returns:
        StrategyParams object with optimized values
        
    Raises:
        ParamsNotFoundError: If params file doesn't exist
    """
    from strategy_core import StrategyParams
    from params.defaults import PARAMETER_DEFAULTS
    
    data = load_params_dict()
    
    # Handle nested 'parameters' key
    if 'parameters' in data:
        params = data['parameters']
    else:
        params = data
    
    # Start with defaults, overlay with file values
    final_params = PARAMETER_DEFAULTS.copy()
    for key, value in params.items():
        if key in final_params:
            final_params[key] = value
    
    # Filter to only StrategyParams fields
    import dataclasses
    valid_fields = {f.name for f in dataclasses.fields(StrategyParams)}
    filtered_params = {k: v for k, v in final_params.items() if k in valid_fields}
    
    return StrategyParams(**filtered_params)


def get_min_confluence() -> int:
    """Get minimum confluence score from params."""
    data = load_params_dict()
    return data.get("min_confluence", 5)


def get_max_concurrent_trades() -> int:
    """Get maximum concurrent trades from params."""
    data = load_params_dict()
    return data.get("max_concurrent_trades", 7)


def get_risk_per_trade_pct() -> float:
    """Get risk per trade percentage from params."""
    data = load_params_dict()
    return data.get("risk_per_trade_pct", 0.5)


def get_transaction_costs(symbol: str) -> Tuple[float, float, float]:
    """
    Get transaction costs for a symbol.
    
    Args:
        symbol: Trading symbol (any format - EURUSD, EUR_USD, etc)
        
    Returns:
        Tuple of (spread_pips, slippage_pips, commission_per_lot)
    """
    data = load_params_dict()
    costs = data.get("transaction_costs", {})
    
    normalized = symbol.replace("_", "").replace(".", "").replace("/", "").upper()
    
    spread_config = costs.get("spread_pips", {})
    spread = spread_config.get(normalized, spread_config.get("default", 2.5))
    slippage = costs.get("slippage_pips", 5.0)  # OPTIMIZED: Increased from 1.0 to 5.0 pips for realistic execution
    commission = costs.get("commission_per_lot", 7.0)
    
    return spread, slippage, commission


def save_optimized_params(
    params_dict: Dict[str, Any],
    backup: bool = True
) -> Path:
    """
    Save optimized parameters to JSON file.
    
    Args:
        params_dict: Dictionary of optimized parameters
        backup: Whether to create backup in history folder
        
    Returns:
        Path to saved file
    """
    from datetime import datetime
    
    params_dict["generated_at"] = datetime.utcnow().isoformat() + "Z"
    params_dict["generated_by"] = "ftmo_challenge_analyzer.py"
    
    if "version" not in params_dict:
        params_dict["version"] = "1.0.0"
    
    with open(PARAMS_FILE, 'w') as f:
        json.dump(params_dict, f, indent=2)
    
    if backup:
        history_dir = Path(__file__).parent / "history"
        history_dir.mkdir(exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = history_dir / f"params_{timestamp}.json"
        with open(backup_path, 'w') as f:
            json.dump(params_dict, f, indent=2)
    
    return PARAMS_FILE
