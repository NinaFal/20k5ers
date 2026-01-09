#!/usr/bin/env python3
"""
Broker Symbol Validator

Connects to your MT5 broker and validates which symbols are available.
Run this FIRST before live trading to:
1. Verify MT5 connection works
2. Get exact symbol names for your broker
3. Update symbol_mapping.py with correct mappings

Usage:
    python scripts/validate_broker_symbols.py
    
    # With specific broker
    BROKER_TYPE=forexcom python scripts/validate_broker_symbols.py
    BROKER_TYPE=fiveers python scripts/validate_broker_symbols.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

# Check if MT5 is available
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    print("⚠️  MetaTrader5 module not installed!")
    print("   Install on Windows: pip install MetaTrader5")
    print("   Note: MT5 only works on Windows with MT5 terminal installed")


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def connect_to_mt5() -> bool:
    """
    Connect to MT5 terminal using environment variables.
    
    Returns:
        True if connection successful, False otherwise
    """
    if not MT5_AVAILABLE:
        return False
    
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    path = os.getenv("MT5_PATH")
    
    if not all([login, password, server]):
        print("❌ Missing MT5 credentials!")
        print("   Set these environment variables in .env:")
        print("   - MT5_LOGIN")
        print("   - MT5_PASSWORD")
        print("   - MT5_SERVER")
        return False
    
    print(f"🔌 Connecting to MT5...")
    print(f"   Server: {server}")
    print(f"   Login:  {login}")
    
    # Initialize with or without path
    init_kwargs = {
        "login": int(login),
        "password": password,
        "server": server,
    }
    if path:
        init_kwargs["path"] = path
    
    if not mt5.initialize(**init_kwargs):
        error = mt5.last_error()
        print(f"❌ MT5 initialization failed!")
        print(f"   Error: {error}")
        print("\n   Troubleshooting:")
        print("   1. Is MT5 terminal installed and running?")
        print("   2. Are credentials correct?")
        print("   3. Is the server name exact (case-sensitive)?")
        return False
    
    return True


def get_account_info() -> Optional[Dict]:
    """Get and display account information."""
    if not MT5_AVAILABLE:
        return None
    
    account = mt5.account_info()
    if account is None:
        print("❌ Could not get account info")
        return None
    
    info = {
        "login": account.login,
        "server": account.server,
        "balance": account.balance,
        "equity": account.equity,
        "margin": account.margin,
        "margin_free": account.margin_free,
        "leverage": account.leverage,
        "currency": account.currency,
        "name": account.name,
        "company": account.company,
    }
    
    print_header("ACCOUNT INFORMATION")
    print(f"  Login:      {info['login']}")
    print(f"  Name:       {info['name']}")
    print(f"  Server:     {info['server']}")
    print(f"  Company:    {info['company']}")
    print(f"  Balance:    ${info['balance']:,.2f} {info['currency']}")
    print(f"  Equity:     ${info['equity']:,.2f}")
    print(f"  Leverage:   1:{info['leverage']}")
    
    return info


def categorize_symbols(symbols) -> Dict[str, List]:
    """
    Categorize MT5 symbols into asset classes.
    
    Returns:
        Dict with keys: forex, metals, indices, crypto, other
    """
    categories = {
        "forex": [],
        "metals": [],
        "indices": [],
        "crypto": [],
        "other": [],
    }
    
    forex_currencies = ['EUR', 'USD', 'GBP', 'JPY', 'CHF', 'AUD', 'NZD', 'CAD']
    metal_keywords = ['XAU', 'XAG', 'GOLD', 'SILVER']
    index_keywords = ['US500', 'US100', 'SPX', 'NAS', 'USTEC', 'DOW', 'DAX', 'FTSE', 'UK100']
    crypto_keywords = ['BTC', 'ETH', 'BITCOIN', 'ETHER', 'CRYPTO', 'XRP', 'LTC', 'ADA']
    
    for s in symbols:
        name = s.name.upper()
        
        # Check forex (two currency codes, typically 6-7 chars)
        currency_matches = sum(1 for c in forex_currencies if c in name)
        if currency_matches >= 2 and len(s.name) <= 10 and '.' not in s.name:
            categories["forex"].append(s)
        elif any(kw in name for kw in metal_keywords):
            categories["metals"].append(s)
        elif any(kw in name for kw in index_keywords):
            categories["indices"].append(s)
        elif any(kw in name for kw in crypto_keywords):
            categories["crypto"].append(s)
        else:
            categories["other"].append(s)
    
    return categories


def validate_symbols() -> Tuple[List, List, Dict]:
    """
    Validate all expected symbols against broker's available symbols.
    
    Returns:
        Tuple of (found_symbols, missing_symbols, symbol_details)
    """
    from symbol_mapping import ALL_TRADABLE_OANDA, get_broker_symbol
    
    broker_type = os.getenv("BROKER_TYPE", "forexcom").lower()
    
    # Get all available symbols from broker
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        print("❌ Could not get symbols from broker")
        return [], [], {}
    
    # Create lookup dict
    broker_symbols = {s.name.upper(): s for s in all_symbols}
    
    found = []
    missing = []
    details = {}
    
    print_header(f"SYMBOL VALIDATION ({broker_type.upper()})")
    print(f"\nTotal symbols available at broker: {len(all_symbols)}")
    print(f"Expected symbols to validate: {len(ALL_TRADABLE_OANDA)}\n")
    
    for internal_sym in ALL_TRADABLE_OANDA:
        expected_broker_sym = get_broker_symbol(internal_sym, broker_type)
        
        # Try exact match first
        if expected_broker_sym.upper() in broker_symbols:
            s = broker_symbols[expected_broker_sym.upper()]
            found.append(internal_sym)
            details[internal_sym] = {
                "broker_symbol": s.name,
                "spread": s.spread,
                "digits": s.digits,
                "trade_mode": s.trade_mode,
                "description": s.description[:50] if s.description else "",
                "tradeable": s.trade_mode > 0,
            }
        else:
            # Try alternative names
            alt_found = False
            base = internal_sym.replace("_", "").upper()
            
            for broker_sym, s in broker_symbols.items():
                if base in broker_sym or broker_sym in base:
                    found.append(internal_sym)
                    details[internal_sym] = {
                        "broker_symbol": s.name,
                        "spread": s.spread,
                        "digits": s.digits,
                        "trade_mode": s.trade_mode,
                        "description": s.description[:50] if s.description else "",
                        "tradeable": s.trade_mode > 0,
                        "alternative": True,
                    }
                    alt_found = True
                    break
            
            if not alt_found:
                missing.append(internal_sym)
                details[internal_sym] = {"broker_symbol": None, "tradeable": False}
    
    return found, missing, details


def print_validation_results(found: List, missing: List, details: Dict):
    """Print validation results in a formatted table."""
    
    print("\n📊 FOUND SYMBOLS:")
    print("-" * 70)
    print(f"{'Internal':<12} | {'Broker':<15} | {'Spread':>7} | {'Digits':>6} | Status")
    print("-" * 70)
    
    for sym in sorted(found):
        d = details[sym]
        status = "✅ OK" if d.get("tradeable") else "⚠️ Not tradeable"
        if d.get("alternative"):
            status += " (alt name)"
        print(f"{sym:<12} | {d['broker_symbol']:<15} | {d['spread']:>7} | {d['digits']:>6} | {status}")
    
    if missing:
        print("\n❌ MISSING SYMBOLS:")
        print("-" * 70)
        for sym in sorted(missing):
            print(f"   {sym} - NOT FOUND at broker")
        print("\n   ⚠️  These symbols may not be available on this broker/account type")
        print("   Consider adding them to 'excluded_symbols' in broker config")
    
    print(f"\n📈 SUMMARY:")
    print(f"   Found:   {len(found)}/{len(found) + len(missing)} symbols")
    print(f"   Missing: {len(missing)} symbols")
    
    tradeable = sum(1 for sym in found if details[sym].get("tradeable"))
    print(f"   Tradeable: {tradeable} symbols")


def print_category_summary(categories: Dict):
    """Print summary by asset category."""
    print_header("SYMBOLS BY CATEGORY")
    
    for cat, symbols in categories.items():
        if symbols:
            tradeable = sum(1 for s in symbols if s.trade_mode > 0)
            print(f"\n{cat.upper()} ({len(symbols)} total, {tradeable} tradeable):")
            
            # Show first 10
            for s in sorted(symbols, key=lambda x: x.name)[:15]:
                status = "✅" if s.trade_mode > 0 else "❌"
                print(f"  {status} {s.name:<15} | Spread: {s.spread:>5} | {s.description[:35] if s.description else ''}")
            
            if len(symbols) > 15:
                print(f"  ... and {len(symbols) - 15} more")


def generate_mapping_template(found: List, missing: List, details: Dict):
    """Generate updated symbol mapping code."""
    broker_type = os.getenv("BROKER_TYPE", "forexcom").lower()
    
    print_header("SYMBOL MAPPING TEMPLATE")
    print("\nCopy this to symbol_mapping.py if corrections needed:\n")
    
    var_name = "OANDA_TO_FOREXCOM" if "forex" in broker_type else "OANDA_TO_FIVEERS"
    print(f"{var_name} = {{")
    
    for sym in sorted(found + missing):
        d = details.get(sym, {})
        broker_sym = d.get("broker_symbol")
        
        if broker_sym:
            print(f'    "{sym}": "{broker_sym}",')
        else:
            print(f'    "{sym}": "???",  # NOT FOUND - check manually!')
    
    print("}")


def main():
    """Main validation workflow."""
    print("\n" + "🔍 " + "=" * 66 + " 🔍")
    print("   BROKER SYMBOL VALIDATOR")
    print("   " + "=" * 64)
    
    broker_type = os.getenv("BROKER_TYPE", "forexcom")
    print(f"\n   Broker Type: {broker_type}")
    print("   " + "=" * 64)
    
    if not MT5_AVAILABLE:
        print("\n⚠️  Cannot validate - MetaTrader5 module not available")
        print("   This script must be run on Windows with MT5 installed")
        
        # Show expected symbols anyway
        from symbol_mapping import ALL_TRADABLE_OANDA, get_broker_symbol
        print("\n📋 Expected symbol mappings:")
        for sym in ALL_TRADABLE_OANDA[:10]:
            broker_sym = get_broker_symbol(sym, broker_type)
            print(f"   {sym} -> {broker_sym}")
        print(f"   ... and {len(ALL_TRADABLE_OANDA) - 10} more")
        return 1
    
    # Connect to MT5
    if not connect_to_mt5():
        return 1
    
    try:
        # Get account info
        account = get_account_info()
        
        # Get all symbols
        all_symbols = mt5.symbols_get()
        
        # Categorize symbols
        categories = categorize_symbols(all_symbols)
        print_category_summary(categories)
        
        # Validate expected symbols
        found, missing, details = validate_symbols()
        print_validation_results(found, missing, details)
        
        # Generate mapping template
        generate_mapping_template(found, missing, details)
        
        print_header("NEXT STEPS")
        if missing:
            print("1. Update symbol_mapping.py with correct broker symbols")
            print("2. Add missing symbols to 'excluded_symbols' in broker_config.py")
            print("3. Re-run this script to verify")
        else:
            print("✅ All symbols validated successfully!")
            print("   You can proceed with demo testing.")
        
        print("\n🚀 Run the bot with:")
        print(f"   BROKER_TYPE={broker_type} python main_live_bot.py --demo")
        
    finally:
        mt5.shutdown()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
