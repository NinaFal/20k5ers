"""
Position Sizing for FTMO Challenge Account.

Calculates lot sizes based on risk parameters and contract specifications.
"""

from typing import Dict, Optional


# CONTRACT_SPECS aligned with simulate_main_live_bot.py
# pip_size = price movement for 1 pip
# pip_value_per_lot = how much $ moves per pip per lot (in USD)
CONTRACT_SPECS = {
    # Forex - XXX/USD pairs - $10/pip/lot
    "EURUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "GBPUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "AUDUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "NZDUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    
    # JPY pairs - pip = 0.01, ~$6.67/pip/lot at USDJPY=150
    "USDJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    "EURJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    "GBPJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    "AUDJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    "NZDJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    "CADJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    "CHFJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67},
    
    # USD/XXX pairs - variable pip value
    "USDCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "USDCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5},
    
    # Cross pairs
    "EURGBP": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 12.5},
    "EURAUD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.5},
    "EURCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5},
    "EURNZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0},
    "EURCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "GBPAUD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.5},
    "GBPCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5},
    "GBPNZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0},
    "GBPCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "AUDCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5},
    "AUDNZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0},
    "AUDCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "NZDCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5},
    "NZDCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    "CADCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0},
    
    # Metals - CRITICAL: correct pip values
    "XAUUSD": {"pip_size": 0.01, "contract_size": 100, "pip_value_per_lot": 1.0},  # $1/pip/lot (100oz)
    "XAGUSD": {"pip_size": 0.01, "contract_size": 5000, "pip_value_per_lot": 50.0},  # $50/pip/lot (5000oz)
    
    # Indices - $1/point
    "US30": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0},
    "US100": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0},
    "US500": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0},
    "SPX500USD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0},
    "NAS100USD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0},
    
    # Crypto
    "BTCUSD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0},
    "ETHUSD": {"pip_size": 0.01, "contract_size": 1, "pip_value_per_lot": 0.01},
}

# Default specs for unknown symbols
DEFAULT_SPEC = {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol format (remove underscores, dots, etc)."""
    return symbol.replace("_", "").replace(".", "").replace("/", "").upper()


def get_contract_specs(symbol: str) -> Dict:
    """Get contract specifications for a symbol."""
    normalized = normalize_symbol(symbol)
    return CONTRACT_SPECS.get(normalized, DEFAULT_SPEC)


def get_pip_value(symbol: str, current_price: float = None) -> float:
    """
    Get pip value per standard lot in USD.
    
    Uses pre-calculated pip_value_per_lot from CONTRACT_SPECS.
    This matches simulate_main_live_bot.py exactly.
    
    Args:
        symbol: Trading symbol
        current_price: Current price (unused, kept for compatibility)
        
    Returns:
        Pip value in USD per standard lot
    """
    specs = get_contract_specs(symbol)
    return specs.get("pip_value_per_lot", 10.0)


def calculate_lot_size(
    symbol: str,
    account_balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
    max_lot: float = 10.0,
    min_lot: float = 0.01,
    existing_positions: int = 0,
    confluence: int = None,
    use_dynamic_scaling: bool = False,
    confluence_base_score: int = 4,
    confluence_scale_per_point: float = 0.15,
    max_confluence_multiplier: float = 1.5,
    min_confluence_multiplier: float = 0.6,
) -> Dict:
    """
    Calculate position size for a trade.
    
    Aligned with simulate_main_live_bot.py for consistent results.
    
    Args:
        symbol: Trading symbol
        account_balance: Current account balance in USD
        risk_percent: Risk per trade as decimal (e.g., 0.006 for 0.6%)
        entry_price: Entry price level
        stop_loss_price: Stop loss price level
        max_lot: Maximum lot size allowed
        min_lot: Minimum lot size
        existing_positions: Number of open positions (for lot reduction)
        confluence: Confluence score (optional, for scaling)
        use_dynamic_scaling: Enable confluence-based risk scaling
        confluence_base_score: Base confluence score (no scaling at this level)
        confluence_scale_per_point: Scale factor per confluence point above base
        max_confluence_multiplier: Maximum risk multiplier
        min_confluence_multiplier: Minimum risk multiplier
        
    Returns:
        Dict with lot_size, risk_usd, stop_pips, actual_risk_pct
    """
    if entry_price is None or stop_loss_price is None:
        return {
            "lot_size": 0.0,
            "risk_usd": 0.0,
            "stop_pips": 0.0,
            "actual_risk_pct": 0.0,
            "error": "Invalid entry or stop loss"
        }
    
    specs = get_contract_specs(symbol)
    pip_size = specs.get("pip_size", 0.0001)
    pip_value_per_lot = specs.get("pip_value_per_lot", 10.0)
    
    stop_distance = abs(entry_price - stop_loss_price)
    
    # Calculate stop in pips
    if pip_size > 0:
        stop_pips = stop_distance / pip_size
    else:
        stop_pips = stop_distance
    
    if stop_pips <= 0:
        return {
            "lot_size": 0.0,
            "risk_usd": 0.0,
            "stop_pips": 0.0,
            "actual_risk_pct": 0.0,
            "error": "Stop loss too close to entry"
        }
    
    # Apply confluence scaling (matching simulate_main_live_bot.py)
    adjusted_risk_percent = risk_percent
    if use_dynamic_scaling and confluence is not None:
        confluence_diff = confluence - confluence_base_score
        multiplier = 1.0 + (confluence_diff * confluence_scale_per_point)
        multiplier = max(min_confluence_multiplier, min(max_confluence_multiplier, multiplier))
        adjusted_risk_percent = risk_percent * multiplier
    
    # Risk in USD
    risk_usd = account_balance * adjusted_risk_percent
    
    # Risk per lot at this stop distance
    risk_per_lot = stop_pips * pip_value_per_lot
    
    if risk_per_lot <= 0:
        return {
            "lot_size": min_lot,
            "risk_usd": risk_usd,
            "stop_pips": stop_pips,
            "actual_risk_pct": risk_percent,
            "error": "Could not calculate risk per lot"
        }
    
    # Lot size calculation (same as simulate_main_live_bot.py)
    lot_size = risk_usd / risk_per_lot
    
    if existing_positions > 0:
        reduction_factor = 1.0 / (existing_positions + 1)
        lot_size = lot_size * reduction_factor
    
    lot_size = round(lot_size, 2)
    lot_size = max(min_lot, min(max_lot, lot_size))
    
    actual_risk_usd = lot_size * risk_per_lot
    actual_risk_pct = actual_risk_usd / account_balance if account_balance > 0 else 0
    
    return {
        "lot_size": lot_size,
        "risk_usd": round(actual_risk_usd, 2),
        "stop_pips": round(stop_pips, 1),
        "actual_risk_pct": round(actual_risk_pct, 4),
    }
