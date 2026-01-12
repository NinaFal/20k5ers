#!/usr/bin/env python3
"""
Find Exact Index Symbol Names on 5ers MT5

This script connects to your 5ers account and lists ALL available symbols
that might be indices, so we can find the exact naming convention.
"""

import MetaTrader5 as mt5
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Get credentials from .env
MT5_SERVER = os.getenv("MT5_SERVER")
MT5_LOGIN = int(os.getenv("MT5_LOGIN"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")

print("=" * 70)
print("5ERS MT5 INDEX SYMBOL DISCOVERY")
print("=" * 70)
print(f"Server: {MT5_SERVER}")
print(f"Login: {MT5_LOGIN}")
print("=" * 70)

# Initialize MT5
if not mt5.initialize():
    print("❌ MT5 initialization failed")
    quit()

# Login
if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print(f"❌ Login failed: {mt5.last_error()}")
    mt5.shutdown()
    quit()

print("✅ Connected to MT5\n")

# Get ALL symbols
all_symbols = mt5.symbols_get()
print(f"Total symbols available: {len(all_symbols)}\n")

# Filter for potential indices
print("=" * 70)
print("POTENTIAL INDEX SYMBOLS (filtered by keywords)")
print("=" * 70)

index_keywords = [
    "US500", "US100", "US30",  # US indices
    "NAS", "SPX", "SP500", "NDX",  # Alternative US names
    "UK100", "FTSE",  # UK
    "GER", "DAX",  # Germany
    "FRA", "CAC",  # France
    "JPN", "NIKKEI",  # Japan
    "AUS", "ASX",  # Australia
    "CASH", "INDEX", "IND",  # Generic index markers
]

found_indices = []

for symbol in all_symbols:
    symbol_name = symbol.name.upper()
    
    # Check if symbol contains any index keyword
    if any(keyword in symbol_name for keyword in index_keywords):
        found_indices.append(symbol)

print(f"\nFound {len(found_indices)} potential index symbols:\n")

if found_indices:
    print(f"{'Symbol Name':<30} | {'Description':<40} | {'Visible'}")
    print("-" * 90)
    
    for sym in sorted(found_indices, key=lambda x: x.name):
        description = sym.description if hasattr(sym, 'description') else sym.path
        visible = "✓" if sym.visible else "✗"
        print(f"{sym.name:<30} | {description:<40} | {visible}")
else:
    print("❌ No index symbols found with standard keywords!")
    print("\nSearching for ALL symbols containing 'cash', '.', or numbers...")
    
    # Broader search
    for symbol in all_symbols:
        name = symbol.name
        if any(x in name.lower() for x in ['cash', '.']) or any(c.isdigit() for c in name):
            if len(name) < 20:  # Exclude very long names
                description = symbol.description if hasattr(symbol, 'description') else symbol.path
                print(f"{name:<30} | {description}")

print("\n" + "=" * 70)
print("SPECIFIC SEARCHES")
print("=" * 70)

# Search for specific patterns
searches = [
    ("US500", "S&P 500"),
    ("US100", "Nasdaq 100"),
    ("NAS100", "Nasdaq 100"),
    ("SPX500", "S&P 500"),
    ("UK100", "FTSE 100"),
]

print("\nLooking for specific index names:")
for search_term, description in searches:
    matches = [s for s in all_symbols if search_term.lower() in s.name.lower()]
    if matches:
        for match in matches:
            print(f"✓ Found: {match.name:<20} ({description})")
    else:
        print(f"✗ Not found: {search_term:<15} ({description})")

print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

if found_indices:
    print("\n✅ Update symbol_mapping.py with these EXACT names:")
    print("\nOANDA_TO_FIVEERS = {")
    
    # Map found symbols to OANDA names
    for idx in sorted(found_indices, key=lambda x: x.name):
        name = idx.name
        if "US500" in name or "SPX" in name or "SP500" in name:
            print(f'    "SPX500_USD": "{name}",')
        elif "US100" in name or "NAS" in name or "NDX" in name:
            print(f'    "NAS100_USD": "{name}",')
        elif "UK100" in name or "FTSE" in name:
            print(f'    "UK100_USD": "{name}",')
    
    print("}")
else:
    print("\n⚠️  No standard index symbols found!")
    print("Please check with 5ers support for available indices on your account.")

mt5.shutdown()
print("\n" + "=" * 70)
print("DONE - Upload this output to help fix symbol_mapping.py")
print("=" * 70)
