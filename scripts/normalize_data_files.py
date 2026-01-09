#!/usr/bin/env python3
"""
Normalize OHLCV data files to MT5 format (EURUSD) - NOT OANDA.
Based on analysis, the code actually loads MT5 format files.
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime

def load_duplicate_analysis():
    """Load the duplicate analysis results."""
    analysis_file = Path('analysis/data_duplicates.json')
    if not analysis_file.exists():
        print("❌ Run find_data_duplicates.py first!")
        return None
    
    with open(analysis_file) as f:
        return json.load(f)

def is_mt5_format(filename):
    """
    Check if filename uses MT5 format (no underscore in symbol).
    EURUSD_H4.csv = True
    EUR_USD_H4.csv = False
    """
    name = filename.replace('.csv', '')
    parts = name.split('_')
    
    # MT5: EURUSD_H4_2003_2025 -> first part is 6+ chars, not 3_3 pattern
    if len(parts) >= 2:
        first_part = parts[0]
        # If first part is exactly 6 chars and all alpha, likely MT5 format
        if len(first_part) == 6 and first_part.isalpha():
            return True
        # Or if it's longer (like SPX500USD, etc)
        if len(first_part) > 6 and first_part[-3:].isupper():
            return True
    
    return False

def normalize_data_files(dry_run=True):
    """
    Keep MT5 format files, remove OANDA format duplicates.
    
    Args:
        dry_run: If True, only show what would be done
    """
    data_dir = Path('data/ohlcv')
    backup_dir = Path('data/ohlcv_backup_oanda_format')
    
    results = load_duplicate_analysis()
    if not results:
        return

    print(f"🔍 Analysis shows ALL duplicate pairs have DIFFERENT data!")
    print(f"   This suggests they may be from different data sources.")
    print(f"   Based on code analysis: normalize to MT5 format (EURUSD)")
    print(f"   Reason: load_ohlcv_data() converts EUR_USD -> EURUSD")
    print()
    
    actions = []
    
    # For each duplicate group, keep MT5, remove OANDA
    for item in results:
        if item.get('identical', False):
            print(f"✅ Identical: {item['normalized_name']} - can safely remove duplicate")
        else:
            print(f"⚠️ Different: {item['normalized_name']} - keeping MT5 format based on code usage")
        
        files = item['files']
        
        # Find MT5 format and OANDA format files
        mt5_files = [f for f in files if is_mt5_format(f['name'])]
        oanda_files = [f for f in files if not is_mt5_format(f['name'])]
        
        if mt5_files and oanda_files:
            # Keep MT5, remove OANDA
            for oanda_file in oanda_files:
                actions.append({
                    'action': 'REMOVE_OANDA',
                    'file': oanda_file['path'],
                    'reason': f"Code uses MT5 format, keeping {mt5_files[0]['name']}",
                })
    
    # Show summary
    print("\n" + "=" * 70)
    print("DATA NORMALIZATION PLAN")
    print("=" * 70)
    print(f"Strategy: KEEP MT5 format (EURUSD), REMOVE OANDA format (EUR_USD)")
    print(f"Reason: load_ohlcv_data() normalizes EUR_USD -> EURUSD")
    
    removes = [a for a in actions if a['action'] == 'REMOVE_OANDA']
    
    print(f"\n📋 Files to REMOVE (OANDA format): {len(removes)}")
    for a in removes[:15]:  # Show first 15
        print(f"   🗑️  {Path(a['file']).name}")
    if len(removes) > 15:
        print(f"   ... and {len(removes) - 15} more")
    
    if dry_run:
        print("\n⚠️ DRY RUN - No changes made")
        print("Run with dry_run=False to execute changes")
        
        # Save plan
        with open('analysis/normalization_plan.json', 'w') as f:
            json.dump(actions, f, indent=2)
        print("✅ Plan saved to: analysis/normalization_plan.json")
        
        return actions
    
    # Execute changes
    print("\n🚀 EXECUTING CHANGES...")
    
    # Create backup directory for removed files
    if removes:
        backup_dir.mkdir(exist_ok=True)
        print(f"📁 Backup directory: {backup_dir}")
    
    # Execute removes (move to backup instead of delete)
    for a in removes:
        src = Path(a['file'])
        dst = backup_dir / src.name
        shutil.move(str(src), str(dst))
        print(f"   ✅ Moved to backup: {src.name}")
    
    print(f"\n✅ Normalization complete!")
    print(f"   Removed OANDA format files: {len(removes)}")
    if removes:
        print(f"   Backup location: {backup_dir}")
    
    return actions

if __name__ == '__main__':
    import sys
    
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("🔍 DRY RUN MODE - showing what would be done")
        print("   Use --execute flag to actually make changes")
        print("")
    
    normalize_data_files(dry_run=dry_run)