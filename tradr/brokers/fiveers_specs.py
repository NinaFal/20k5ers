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
    "XAU": {  # Gold - 5ers uses 100oz per lot
        "pip_size": 0.01,             # $0.01 (1 cent)
        "pip_value_per_lot": 100.0,   # $100 per pip per lot (100oz × $1 per oz per $0.01 move)
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
    },
    "XAG": {  # Silver - 5ers uses 5000oz per lot
        "pip_size": 0.001,            # $0.001 (tick is 0.0001, pip = 10 ticks)
        "pip_value_per_lot": 5.0,     # $5 per pip per lot ($0.001 × 5000oz)
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
