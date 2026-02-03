"""
5ers Broker-Specific Contract Specifications

5ers uses MINI contracts for indices, different from standard CFD specs.
These specs are based on actual MT5 platform observations.
"""

# 5ERS SPECIFIC CONTRACT SPECS
FIVEERS_CONTRACT_SPECS = {
    # INDICES - 5ers uses MINI contracts ($1/point instead of $10-$20/point)
    "NAS100": {
        "pip_size": 1.0,              # 1 point = 1.0 index point
        "pip_value_per_lot": 1.0,     # $1 per point per lot (MINI contract)
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    "SPX500": {
        "pip_size": 1.0,              # 1 point = 1.0 index point
        "pip_value_per_lot": 1.0,     # $1 per point per lot (MINI contract)
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    "UK100": {
        "pip_size": 1.0,
        "pip_value_per_lot": 1.40,    # £1/point * GBPUSD(~1.40) = $1.40/point (GBP-denominated index)
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    
    # FOREX - Standard 0.0001 pip, $10 per lot
    "FOREX": {
        "pip_size": 0.0001,
        "pip_value_per_lot": 10.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    
    # JPY pairs - 0.01 pip
    "FOREX_JPY": {
        "pip_size": 0.01,
        "pip_value_per_lot": 10.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    
    # METALS
    # CRITICAL: pip_size defines what "1 pip" means. pip_value is profit per pip per lot.
    # XAU: $100 per POINT (1.00 move), pip_size=0.01, so 1 point = 100 pips
    # Therefore: pip_value = $100/point / 100 pips = $1.00/pip
    "XAU": {  # Gold - 5ers: 100oz per lot, $100 per point = $1 per pip
        "pip_size": 0.01,             # 1 pip = $0.01 price movement
        "pip_value_per_lot": 1.0,     # $1.00 per pip per lot (verified: 478 pips × $1 × 0.2 lots = $95.60)
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    # XAG: From trade: 0.176 point move = -$44 at 0.05 lots
    # So pip_value = $44 / 176 pips / 0.05 = $5/pip (if pip_size = 0.001)
    "XAG": {  # Silver - 5ers: 5000oz, $5 per pip
        "pip_size": 0.001,            # 1 pip = $0.001 price movement
        "pip_value_per_lot": 5.0,     # $5.00 per pip per lot (verified: 176 pips × $5 × 0.05 = $44)
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    
    # CRYPTO
    "BTC": {
        "pip_size": 1.0,
        "pip_value_per_lot": 1.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    "ETH": {
        "pip_size": 0.01,
        "pip_value_per_lot": 1.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
}


def get_fiveers_contract_specs(symbol: str) -> dict:
    """
    Get 5ers-specific contract specifications for a symbol.
    
    Args:
        symbol: Symbol name (e.g., "NAS100_USD", "EURUSD")
        
    Returns:
        Contract specs dict with pip_size, pip_value_per_lot, etc.
    """
    # Normalize symbol
    symbol_upper = symbol.upper().replace("_", "").replace("USD", "")
    
    # Indices
    if "NAS100" in symbol_upper or "NDX" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["NAS100"]
    elif "SPX500" in symbol_upper or "SP500" in symbol_upper or "SPX" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["SPX500"]
    elif "UK100" in symbol_upper or "FTSE" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["UK100"]
    
    # Metals
    elif "XAU" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["XAU"]
    elif "XAG" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["XAG"]
    
    # Crypto
    elif "BTC" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["BTC"]
    elif "ETH" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["ETH"]
    
    # Forex
    elif "JPY" in symbol_upper:
        return FIVEERS_CONTRACT_SPECS["FOREX_JPY"]
    else:
        return FIVEERS_CONTRACT_SPECS["FOREX"]
