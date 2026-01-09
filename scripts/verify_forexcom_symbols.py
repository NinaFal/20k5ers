#!/usr/bin/env python3
"""
Verify Forex.com symbol names by connecting to MT5.

This script will:
1. Connect to Forex.com demo
2. List all available symbols
3. Check which symbols match our mappings
4. Identify any mismatches

Run AFTER configuring .env with Forex.com credentials!
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker_config import get_broker_config, BrokerType
from symbol_mapping import ALL_TRADABLE_OANDA, get_broker_symbol
import MetaTrader5 as mt5


def verify_forexcom_symbols():
    """Verify which symbols are available on Forex.com demo."""
    
    # Get Forex.com config
    config = get_broker_config(BrokerType.FOREXCOM_DEMO)
    
    print("=" * 70)
    print("FOREX.COM SYMBOL VERIFICATION")
    print("=" * 70)
    config.print_summary()
    
    # Connect to MT5
    print("\n🔌 Connecting to MT5...")
    if not mt5.initialize():
        print(f"❌ MT5 initialize() failed: {mt5.last_error()}")
        return False
    
    print(f"✅ MT5 initialized")
    
    # Login
    if not mt5.login(
        config.mt5_login,
        password=config.mt5_password,
        server=config.mt5_server
    ):
        print(f"❌ Login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    
    print(f"✅ Logged in to {config.mt5_server}")
    
    # Get all symbols
    all_symbols = mt5.symbols_get()
    print(f"\n📊 Total symbols available: {len(all_symbols)}")
    
    # Check our mappings
    print("\n" + "=" * 70)
    print("SYMBOL MAPPING VERIFICATION")
    print("=" * 70)
    
    found = []
    not_found = []
    alternatives = []
    
    for internal_sym in ALL_TRADABLE_OANDA:
        expected_broker_sym = get_broker_symbol(internal_sym, "forexcom")
        
        # Check if symbol exists
        symbol_info = mt5.symbol_info(expected_broker_sym)
        
        if symbol_info:
            found.append((internal_sym, expected_broker_sym, "✅"))
        else:
            # Try to find alternatives
            possible = []
            base = internal_sym.replace("_", "")
            
            for sym in all_symbols:
                if base.lower() in sym.name.lower():
                    possible.append(sym.name)
            
            if possible:
                alternatives.append((internal_sym, expected_broker_sym, possible))
            else:
                not_found.append((internal_sym, expected_broker_sym))
    
    # Print results
    print(f"\n✅ FOUND ({len(found)} symbols):")
    print(f"{'Internal':<15} | {'Broker Symbol':<20} | Status")
    print("-" * 60)
    for internal, broker, status in found:
        print(f"{internal:<15} | {broker:<20} | {status}")
    
    if alternatives:
        print(f"\n⚠️  NEEDS CORRECTION ({len(alternatives)} symbols):")
        print(f"{'Internal':<15} | {'Expected':<20} | Alternatives")
        print("-" * 70)
        for internal, expected, alts in alternatives:
            alts_str = ", ".join(alts[:3])  # Show first 3
            print(f"{internal:<15} | {expected:<20} | {alts_str}")
    
    if not_found:
        print(f"\n❌ NOT AVAILABLE ({len(not_found)} symbols):")
        print(f"{'Internal':<15} | {'Expected Broker Symbol':<20}")
        print("-" * 60)
        for internal, broker in not_found:
            print(f"{internal:<15} | {broker:<20}")
    
    # Suggested mapping corrections
    if alternatives:
        print("\n" + "=" * 70)
        print("SUGGESTED MAPPING CORRECTIONS FOR symbol_mapping.py:")
        print("=" * 70)
        print("\nOANDA_TO_FOREXCOM = {")
        for internal, expected, alts in alternatives:
            print(f'    "{internal}": "{alts[0]}",  # was: {expected}')
        print("}")
    
    # Cleanup
    mt5.shutdown()
    print("\n✅ Verification complete!")
    
    return True


if __name__ == "__main__":
    verify_forexcom_symbols()
