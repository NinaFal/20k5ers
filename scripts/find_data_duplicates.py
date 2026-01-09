#!/usr/bin/env python3
"""
Find duplicate OHLCV data files with different naming conventions.
Compares EUR_USD format vs EURUSD format.
"""

import os
import hashlib
from pathlib import Path
from collections import defaultdict
import pandas as pd

def get_file_hash(filepath, num_rows=1000):
    """Get hash of first N rows to compare files."""
    try:
        df = pd.read_csv(filepath, nrows=num_rows)
        return hashlib.md5(df.to_string().encode()).hexdigest()
    except Exception as e:
        return f"ERROR: {e}"

def normalize_symbol(filename):
    """
    Normalize symbol name to find potential duplicates.
    EUR_USD_H4 and EURUSD_H4 both become EURUSD_H4
    """
    # Remove extension
    name = filename.replace('.csv', '').replace('.parquet', '')
    
    # Remove underscores from currency pairs (but keep timeframe underscore)
    parts = name.split('_')
    
    # Try to identify the pattern
    # EUR_USD_H4_2003_2025 -> parts = ['EUR', 'USD', 'H4', '2003', '2025']
    # EURUSD_H4_2003_2025 -> parts = ['EURUSD', 'H4', '2003', '2025']
    
    if len(parts) >= 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
        # EUR_USD format - combine first two
        symbol = parts[0] + parts[1]
        rest = '_'.join(parts[2:])
        return f"{symbol}_{rest}"
    else:
        return name

def find_duplicates(data_dir='data/ohlcv'):
    """Find all potential duplicate files."""
    data_path = Path(data_dir)
    
    if not data_path.exists():
        print(f"❌ Directory not found: {data_dir}")
        return {}
    
    # Group files by normalized name
    groups = defaultdict(list)
    
    for f in data_path.glob('*.csv'):
        normalized = normalize_symbol(f.name)
        groups[normalized].append(f)
    
    # Find groups with multiple files (duplicates)
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    
    return duplicates

def analyze_duplicates(duplicates):
    """Analyze duplicate files to verify they contain same data."""
    results = []
    
    for normalized_name, files in duplicates.items():
        print(f"\n🔍 Analyzing: {normalized_name}")
        
        file_info = []
        for f in files:
            size = f.stat().st_size
            hash_val = get_file_hash(f)
            
            try:
                df = pd.read_csv(f)
                rows = len(df)
                cols = list(df.columns)
                date_range = f"{df.iloc[0, 0]} to {df.iloc[-1, 0]}" if len(df) > 0 else "empty"
            except Exception as e:
                rows = 0
                cols = []
                date_range = f"ERROR: {e}"
            
            file_info.append({
                'path': str(f),
                'name': f.name,
                'size': size,
                'hash': hash_val,
                'rows': rows,
                'date_range': date_range,
            })
            
            print(f"   📄 {f.name}")
            print(f"      Size: {size:,} bytes | Rows: {rows:,}")
            print(f"      Hash: {hash_val[:16]}...")
        
        # Check if files are identical
        hashes = [fi['hash'] for fi in file_info]
        all_same = len(set(hashes)) == 1 and not hashes[0].startswith('ERROR')
        
        results.append({
            'normalized_name': normalized_name,
            'files': file_info,
            'identical': all_same,
            'recommendation': 'KEEP_OANDA_FORMAT' if all_same else 'MANUAL_REVIEW'
        })
        
        if all_same:
            print(f"   ✅ Files are IDENTICAL - safe to remove duplicate")
        else:
            print(f"   ⚠️ Files DIFFER - manual review needed!")
    
    return results

def main():
    print("=" * 70)
    print("DATA DUPLICATE ANALYSIS")
    print("=" * 70)
    
    duplicates = find_duplicates()
    
    if not duplicates:
        print("\n✅ No duplicates found!")
        return
    
    print(f"\nFound {len(duplicates)} groups of potential duplicates")
    
    results = analyze_duplicates(duplicates)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    identical = [r for r in results if r['identical']]
    different = [r for r in results if not r['identical']]
    
    print(f"\n✅ Identical duplicates (safe to clean): {len(identical)}")
    for r in identical:
        oanda_file = [f for f in r['files'] if '_' in f['name'].split('_')[0][:4] or len(f['name'].split('_')[0]) > 3]
        mt5_file = [f for f in r['files'] if f not in oanda_file]
        if mt5_file:
            print(f"   Keep: {oanda_file[0]['name'] if oanda_file else r['files'][0]['name']}")
            print(f"   Remove: {mt5_file[0]['name']}")
    
    if different:
        print(f"\n⚠️ Different files (need review): {len(different)}")
        for r in different:
            print(f"   {r['normalized_name']}: {[f['name'] for f in r['files']]}")
    
    # Save results
    import json
    with open('analysis/data_duplicates.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to: analysis/data_duplicates.json")

if __name__ == '__main__':
    main()