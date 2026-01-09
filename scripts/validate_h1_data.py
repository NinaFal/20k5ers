#!/usr/bin/env python3
"""
Validate H1 data against D1 and H4 data.

Checks:
1. H1 high/low aggregated to daily should match D1 high/low
2. H1 high/low aggregated to 4-hour should match H4 high/low
3. Timestamps should be consistent
4. No large gaps in data
5. Price continuity (no sudden jumps)
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np
from tqdm import tqdm

DATA_DIR = Path('data/ohlcv')

# Tolerance for price comparison (percentage)
PRICE_TOLERANCE_PCT = 0.5  # 0.5% tolerance for rounding differences


def load_data(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """Load OHLCV data for a symbol and timeframe."""
    # Convert OANDA format (EUR_USD) to MT5 format (EURUSD) if needed
    # All data files use MT5 naming (no underscores)
    mt5_symbol = symbol.replace('_', '')
    
    # Try different filename patterns (all use MT5 format now)
    patterns = [
        f"{mt5_symbol}_{timeframe}_2014_2025.csv",
        f"{mt5_symbol}_{timeframe}_2003_2025.csv",
        f"{mt5_symbol}_{timeframe}.csv",
    ]
    
    for pattern in patterns:
        filepath = DATA_DIR / pattern
        if filepath.exists():
            df = pd.read_csv(filepath)
            
            # Normalize column names (MT5 uses 'time' and capitalized OHLCV)
            if 'time' in df.columns:
                df = df.rename(columns={'time': 'timestamp'})
            
            # Lowercase OHLCV columns for internal consistency
            rename_map = {
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
            }
            df = df.rename(columns=rename_map)
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
    
    return None


def aggregate_h1_to_daily(h1_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate H1 data to daily OHLCV."""
    df = h1_df.copy()
    df['date'] = df['timestamp'].dt.date
    
    daily = df.groupby('date').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).reset_index()
    
    daily['date'] = pd.to_datetime(daily['date'])
    return daily


def aggregate_h1_to_h4(h1_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate H1 data to H4 OHLCV."""
    df = h1_df.copy()
    
    # Round timestamp down to nearest 4-hour block
    df['h4_timestamp'] = df['timestamp'].dt.floor('4H')
    
    h4 = df.groupby('h4_timestamp').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).reset_index()
    
    h4 = h4.rename(columns={'h4_timestamp': 'timestamp'})
    return h4


def compare_prices(
    actual: float,
    expected: float,
    tolerance_pct: float = PRICE_TOLERANCE_PCT,
) -> Tuple[bool, float]:
    """
    Compare two prices with tolerance.
    
    Returns:
        (is_match, difference_pct)
    """
    if expected == 0:
        return actual == 0, 0.0
    
    diff_pct = abs(actual - expected) / expected * 100
    is_match = diff_pct <= tolerance_pct
    
    return is_match, diff_pct


def validate_h1_vs_d1(symbol: str) -> Dict:
    """
    Validate H1 data against D1 data.
    
    Check that:
    - Max H1 high for each day == D1 high
    - Min H1 low for each day == D1 low
    """
    h1_df = load_data(symbol, 'H1')
    d1_df = load_data(symbol, 'D1')
    
    if h1_df is None:
        return {'status': 'SKIP', 'reason': 'No H1 data'}
    if d1_df is None:
        return {'status': 'SKIP', 'reason': 'No D1 data'}
    
    # Aggregate H1 to daily
    h1_daily = aggregate_h1_to_daily(h1_df)
    
    # Normalize D1 dates
    d1_df['date'] = pd.to_datetime(d1_df['timestamp']).dt.date
    d1_df['date'] = pd.to_datetime(d1_df['date'])
    
    # Merge on date
    merged = h1_daily.merge(
        d1_df[['date', 'high', 'low']],
        left_on='date',
        right_on='date',
        how='inner',
        suffixes=('_h1', '_d1'),
    )
    
    if len(merged) == 0:
        return {'status': 'ERROR', 'reason': 'No overlapping dates'}
    
    # Compare highs and lows
    issues = []
    high_diffs = []
    low_diffs = []
    
    for _, row in merged.iterrows():
        # Check high
        high_match, high_diff = compare_prices(row['high_h1'], row['high_d1'])
        high_diffs.append(high_diff)
        
        if not high_match:
            issues.append({
                'date': str(row['date'].date()),
                'type': 'HIGH_MISMATCH',
                'h1_value': row['high_h1'],
                'd1_value': row['high_d1'],
                'diff_pct': high_diff,
            })
        
        # Check low
        low_match, low_diff = compare_prices(row['low_h1'], row['low_d1'])
        low_diffs.append(low_diff)
        
        if not low_match:
            issues.append({
                'date': str(row['date'].date()),
                'type': 'LOW_MISMATCH',
                'h1_value': row['low_h1'],
                'd1_value': row['low_d1'],
                'diff_pct': low_diff,
            })
    
    return {
        'status': 'PASS' if len(issues) == 0 else 'FAIL',
        'total_days': len(merged),
        'issues_count': len(issues),
        'issues': issues[:20],  # Limit to first 20
        'avg_high_diff_pct': np.mean(high_diffs),
        'avg_low_diff_pct': np.mean(low_diffs),
        'max_high_diff_pct': np.max(high_diffs),
        'max_low_diff_pct': np.max(low_diffs),
    }


def validate_h1_vs_h4(symbol: str) -> Dict:
    """
    Validate H1 data against H4 data.
    
    Check that:
    - Max H1 high for each 4-hour block == H4 high
    - Min H1 low for each 4-hour block == H4 low
    """
    h1_df = load_data(symbol, 'H1')
    h4_df = load_data(symbol, 'H4')
    
    if h1_df is None:
        return {'status': 'SKIP', 'reason': 'No H1 data'}
    if h4_df is None:
        return {'status': 'SKIP', 'reason': 'No H4 data'}
    
    # Aggregate H1 to H4
    h1_h4 = aggregate_h1_to_h4(h1_df)
    
    # Normalize H4 timestamps
    h4_df['timestamp'] = pd.to_datetime(h4_df['timestamp']).dt.floor('4H')
    
    # Merge
    merged = h1_h4.merge(
        h4_df[['timestamp', 'high', 'low']],
        on='timestamp',
        how='inner',
        suffixes=('_h1', '_h4'),
    )
    
    if len(merged) == 0:
        return {'status': 'ERROR', 'reason': 'No overlapping timestamps'}
    
    # Compare
    issues = []
    high_diffs = []
    low_diffs = []
    
    for _, row in merged.iterrows():
        high_match, high_diff = compare_prices(row['high_h1'], row['high_h4'])
        low_match, low_diff = compare_prices(row['low_h1'], row['low_h4'])
        
        high_diffs.append(high_diff)
        low_diffs.append(low_diff)
        
        if not high_match or not low_match:
            issues.append({
                'timestamp': str(row['timestamp']),
                'type': 'HIGH_MISMATCH' if not high_match else 'LOW_MISMATCH',
                'h1_high': row['high_h1'],
                'h4_high': row['high_h4'],
                'h1_low': row['low_h1'],
                'h4_low': row['low_h4'],
            })
    
    return {
        'status': 'PASS' if len(issues) == 0 else 'FAIL',
        'total_bars': len(merged),
        'issues_count': len(issues),
        'issues': issues[:20],
        'avg_high_diff_pct': np.mean(high_diffs),
        'avg_low_diff_pct': np.mean(low_diffs),
    }


def check_data_gaps(symbol: str) -> Dict:
    """Check for gaps in H1 data (missing hours)."""
    h1_df = load_data(symbol, 'H1')
    
    if h1_df is None:
        return {'status': 'SKIP', 'reason': 'No H1 data'}
    
    df = h1_df.sort_values('timestamp').reset_index(drop=True)
    
    # Calculate time differences
    df['time_diff'] = df['timestamp'].diff()
    
    # Expected diff is 1 hour, but weekends and holidays are OK
    # Flag gaps > 72 hours (3 days) as potential issues
    gap_threshold = timedelta(hours=72)
    
    gaps = df[df['time_diff'] > gap_threshold]
    
    gap_list = []
    for _, row in gaps.iterrows():
        gap_list.append({
            'after': str(df.loc[row.name - 1, 'timestamp']) if row.name > 0 else 'N/A',
            'before': str(row['timestamp']),
            'gap_hours': row['time_diff'].total_seconds() / 3600,
        })
    
    return {
        'status': 'PASS' if len(gaps) == 0 else 'WARN',
        'total_candles': len(df),
        'large_gaps': len(gaps),
        'gaps': gap_list[:10],
        'date_range': f"{df['timestamp'].min()} to {df['timestamp'].max()}",
    }


def check_timestamp_consistency(symbol: str) -> Dict:
    """Check that timestamps are consistent across timeframes."""
    h1_df = load_data(symbol, 'H1')
    d1_df = load_data(symbol, 'D1')
    h4_df = load_data(symbol, 'H4')
    
    issues = []
    
    # Check H1 date range
    if h1_df is not None:
        h1_start = h1_df['timestamp'].min()
        h1_end = h1_df['timestamp'].max()
    else:
        return {'status': 'SKIP', 'reason': 'No H1 data'}
    
    # Compare with D1 date range
    if d1_df is not None:
        d1_start = pd.to_datetime(d1_df['timestamp']).min()
        d1_end = pd.to_datetime(d1_df['timestamp']).max()
        
        if h1_start.date() > d1_start.date():
            issues.append(f"H1 starts later than D1: {h1_start.date()} vs {d1_start.date()}")
        if h1_end.date() < d1_end.date():
            issues.append(f"H1 ends earlier than D1: {h1_end.date()} vs {d1_end.date()}")
    
    # Compare with H4 date range
    if h4_df is not None:
        h4_start = pd.to_datetime(h4_df['timestamp']).min()
        h4_end = pd.to_datetime(h4_df['timestamp']).max()
        
        if h1_start > h4_start:
            issues.append(f"H1 starts later than H4: {h1_start} vs {h4_start}")
        if h1_end < h4_end:
            issues.append(f"H1 ends earlier than H4: {h1_end} vs {h4_end}")
    
    return {
        'status': 'PASS' if len(issues) == 0 else 'WARN',
        'h1_range': f"{h1_start} to {h1_end}",
        'h1_candles': len(h1_df),
        'issues': issues,
    }


def validate_all_assets(assets: List[str] = None) -> Dict:
    """Run all validations on all assets."""
    if assets is None:
        # Find all H1 files
        h1_files = list(DATA_DIR.glob('*_H1_*.csv'))
        assets = [f.stem.split('_H1_')[0] for f in h1_files]
        assets = list(set(assets))
    
    print(f"{'='*70}")
    print(f"VALIDATING H1 DATA FOR {len(assets)} ASSETS")
    print(f"{'='*70}\n")
    
    results = {}
    
    for asset in tqdm(assets, desc="Validating"):
        print(f"\n📊 {asset}")
        
        results[asset] = {
            'h1_vs_d1': validate_h1_vs_d1(asset),
            'h1_vs_h4': validate_h1_vs_h4(asset),
            'data_gaps': check_data_gaps(asset),
            'timestamp_consistency': check_timestamp_consistency(asset),
        }
        
        # Print quick summary
        d1_status = results[asset]['h1_vs_d1']['status']
        h4_status = results[asset]['h1_vs_h4']['status']
        gaps_status = results[asset]['data_gaps']['status']
        
        status_icon = {
            'PASS': '✅',
            'FAIL': '❌',
            'WARN': '⚠️',
            'SKIP': '⏭️',
            'ERROR': '🔴',
        }
        
        print(f"   D1 check: {status_icon.get(d1_status, '?')} {d1_status}")
        print(f"   H4 check: {status_icon.get(h4_status, '?')} {h4_status}")
        print(f"   Gaps:     {status_icon.get(gaps_status, '?')} {gaps_status}")
    
    # Summary
    print(f"\n{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}")
    
    d1_pass = sum(1 for r in results.values() if r['h1_vs_d1']['status'] == 'PASS')
    d1_fail = sum(1 for r in results.values() if r['h1_vs_d1']['status'] == 'FAIL')
    h4_pass = sum(1 for r in results.values() if r['h1_vs_h4']['status'] == 'PASS')
    h4_fail = sum(1 for r in results.values() if r['h1_vs_h4']['status'] == 'FAIL')
    
    print(f"\nH1 vs D1: {d1_pass} PASS, {d1_fail} FAIL")
    print(f"H1 vs H4: {h4_pass} PASS, {h4_fail} FAIL")
    
    # Failed assets
    failed_d1 = [a for a, r in results.items() if r['h1_vs_d1']['status'] == 'FAIL']
    failed_h4 = [a for a, r in results.items() if r['h1_vs_h4']['status'] == 'FAIL']
    
    if failed_d1:
        print(f"\n❌ Failed D1 validation: {failed_d1}")
    if failed_h4:
        print(f"❌ Failed H4 validation: {failed_h4}")
    
    # Save results
    output_file = Path('analysis/h1_validation_results.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✅ Results saved to: {output_file}")
    
    return results


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate H1 data')
    parser.add_argument('--asset', type=str, help='Validate single asset')
    
    args = parser.parse_args()
    
    if args.asset:
        results = validate_all_assets([args.asset])
    else:
        results = validate_all_assets()
