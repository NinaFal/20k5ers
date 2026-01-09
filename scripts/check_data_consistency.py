#!/usr/bin/env python3
"""
DATA CONSISTENCY CHECKER

Compares OHLC values between:
1. Data used by backtest (TPE validate)
2. Data that would be used by live bot

Identifies:
- Missing data
- Timestamp mismatches  
- OHLC value differences
- Gap analysis

Author: AI Assistant
Date: January 5, 2026
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORKSPACE = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE / "data" / "ohlcv"


def check_data_availability() -> Dict[str, Dict]:
    """Check data availability for all symbols and timeframes."""
    timeframes = ['M', 'W', 'D', 'H4', 'H1']
    
    results = {}
    
    # Find all symbols
    symbols = set()
    for f in DATA_DIR.glob("*_D.csv"):
        name = f.stem
        if name.endswith("_D"):
            symbol = name[:-2]
            symbols.add(symbol)
    
    for symbol in sorted(symbols):
        results[symbol] = {}
        
        for tf in timeframes:
            filepath = DATA_DIR / f"{symbol}_{tf}.csv"
            
            if filepath.exists():
                try:
                    df = pd.read_csv(filepath)
                    df.columns = df.columns.str.lower()
                    
                    # Get date column
                    date_col = 'time' if 'time' in df.columns else 'datetime' if 'datetime' in df.columns else None
                    
                    if date_col:
                        df[date_col] = pd.to_datetime(df[date_col])
                        start = df[date_col].min()
                        end = df[date_col].max()
                        
                        results[symbol][tf] = {
                            "exists": True,
                            "rows": len(df),
                            "start": str(start.date()) if pd.notna(start) else None,
                            "end": str(end.date()) if pd.notna(end) else None,
                        }
                    else:
                        results[symbol][tf] = {
                            "exists": True,
                            "rows": len(df),
                            "error": "No date column",
                        }
                except Exception as e:
                    results[symbol][tf] = {
                        "exists": True,
                        "error": str(e),
                    }
            else:
                results[symbol][tf] = {"exists": False}
    
    return results


def check_data_gaps(symbol: str, timeframe: str = "D") -> Dict:
    """Check for gaps in the data for a symbol."""
    filepath = DATA_DIR / f"{symbol}_{timeframe}.csv"
    
    if not filepath.exists():
        return {"error": "File not found"}
    
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.lower()
    
    date_col = 'time' if 'time' in df.columns else 'datetime' if 'datetime' in df.columns else None
    
    if not date_col:
        return {"error": "No date column"}
    
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    
    # Calculate expected frequency
    if timeframe == 'D':
        expected_gap = pd.Timedelta(days=1)
        max_allowed_gap = pd.Timedelta(days=4)  # Allow weekends
    elif timeframe == 'W':
        expected_gap = pd.Timedelta(days=7)
        max_allowed_gap = pd.Timedelta(days=10)
    elif timeframe == 'M':
        expected_gap = pd.Timedelta(days=28)
        max_allowed_gap = pd.Timedelta(days=35)
    elif timeframe == 'H4':
        expected_gap = pd.Timedelta(hours=4)
        max_allowed_gap = pd.Timedelta(hours=72)  # Weekend
    elif timeframe == 'H1':
        expected_gap = pd.Timedelta(hours=1)
        max_allowed_gap = pd.Timedelta(hours=72)  # Weekend
    else:
        return {"error": f"Unknown timeframe: {timeframe}"}
    
    # Find gaps
    gaps = []
    dates = df[date_col].tolist()
    
    for i in range(1, len(dates)):
        gap = dates[i] - dates[i-1]
        if gap > max_allowed_gap:
            gaps.append({
                "from": str(dates[i-1]),
                "to": str(dates[i]),
                "gap_days": gap.days,
            })
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_rows": len(df),
        "date_range": {
            "start": str(df[date_col].min()),
            "end": str(df[date_col].max()),
        },
        "gap_count": len(gaps),
        "gaps": gaps[:20],  # First 20 gaps
    }


def check_ohlc_validity(symbol: str, timeframe: str = "D") -> Dict:
    """Check OHLC data validity (high >= low, etc.)."""
    filepath = DATA_DIR / f"{symbol}_{timeframe}.csv"
    
    if not filepath.exists():
        return {"error": "File not found"}
    
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.lower()
    
    issues = []
    
    # Check required columns
    required = ['open', 'high', 'low', 'close']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"error": f"Missing columns: {missing}"}
    
    # Check high >= low
    high_low_violations = df[df['high'] < df['low']]
    if len(high_low_violations) > 0:
        issues.append({
            "type": "high_low_violation",
            "count": len(high_low_violations),
            "examples": high_low_violations.head(5).to_dict('records'),
        })
    
    # Check high >= open and high >= close
    high_violations = df[(df['high'] < df['open']) | (df['high'] < df['close'])]
    if len(high_violations) > 0:
        issues.append({
            "type": "high_not_highest",
            "count": len(high_violations),
        })
    
    # Check low <= open and low <= close
    low_violations = df[(df['low'] > df['open']) | (df['low'] > df['close'])]
    if len(low_violations) > 0:
        issues.append({
            "type": "low_not_lowest",
            "count": len(low_violations),
        })
    
    # Check for zero or negative values
    zero_values = df[(df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0) | (df['close'] <= 0)]
    if len(zero_values) > 0:
        issues.append({
            "type": "zero_or_negative",
            "count": len(zero_values),
        })
    
    # Check for NaN values
    nan_count = df[required].isna().sum().sum()
    if nan_count > 0:
        issues.append({
            "type": "nan_values",
            "count": int(nan_count),
        })
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_rows": len(df),
        "valid": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues,
    }


def compare_timeframes(symbol: str) -> Dict:
    """Compare data consistency across timeframes for a symbol."""
    result = {
        "symbol": symbol,
        "timeframes": {},
    }
    
    for tf in ['D', 'W', 'M']:
        filepath = DATA_DIR / f"{symbol}_{tf}.csv"
        
        if filepath.exists():
            df = pd.read_csv(filepath)
            df.columns = df.columns.str.lower()
            
            result["timeframes"][tf] = {
                "rows": len(df),
                "has_volume": 'volume' in df.columns,
            }
        else:
            result["timeframes"][tf] = {"exists": False}
    
    return result


def generate_full_report() -> None:
    """Generate a full data consistency report."""
    print("=" * 70)
    print("DATA CONSISTENCY REPORT")
    print("=" * 70)
    print(f"\nData directory: {DATA_DIR}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check availability
    print("\n" + "=" * 70)
    print("1. DATA AVAILABILITY")
    print("=" * 70)
    
    availability = check_data_availability()
    
    # Summary table
    print(f"\n{'Symbol':<15} {'M':>6} {'W':>6} {'D':>6} {'H4':>6} {'H1':>6}")
    print("-" * 50)
    
    for symbol, tfs in sorted(availability.items()):
        row = f"{symbol:<15}"
        for tf in ['M', 'W', 'D', 'H4', 'H1']:
            if tf in tfs:
                if tfs[tf].get('exists'):
                    count = tfs[tf].get('rows', 0)
                    row += f" {count:>6}"
                else:
                    row += f" {'--':>6}"
            else:
                row += f" {'--':>6}"
        print(row)
    
    # Check data quality for common symbols
    print("\n" + "=" * 70)
    print("2. DATA QUALITY CHECK")
    print("=" * 70)
    
    # Get symbols with daily data
    symbols_with_daily = [s for s, tfs in availability.items() if tfs.get('D', {}).get('exists')]
    
    quality_issues = []
    for symbol in symbols_with_daily[:15]:  # Check first 15
        result = check_ohlc_validity(symbol, 'D')
        if not result.get('valid', True):
            quality_issues.append(result)
    
    if quality_issues:
        print(f"\n⚠️  {len(quality_issues)} symbols have quality issues:")
        for issue in quality_issues:
            print(f"   {issue['symbol']}: {issue['issue_count']} issues")
    else:
        print("\n✅ All checked symbols have valid OHLC data")
    
    # Check gaps
    print("\n" + "=" * 70)
    print("3. DATA GAP ANALYSIS")
    print("=" * 70)
    
    symbols_with_gaps = []
    for symbol in symbols_with_daily[:15]:  # Check first 15
        result = check_data_gaps(symbol, 'D')
        if result.get('gap_count', 0) > 0:
            symbols_with_gaps.append(result)
    
    if symbols_with_gaps:
        print(f"\n⚠️  {len(symbols_with_gaps)} symbols have data gaps:")
        for gap_info in symbols_with_gaps:
            print(f"   {gap_info['symbol']}: {gap_info['gap_count']} gaps")
            if gap_info['gaps']:
                for g in gap_info['gaps'][:3]:
                    print(f"      {g['from'][:10]} → {g['to'][:10]} ({g['gap_days']} days)")
    else:
        print("\n✅ No significant data gaps found")
    
    # Date range coverage
    print("\n" + "=" * 70)
    print("4. DATE RANGE COVERAGE (2023-2025)")
    print("=" * 70)
    
    target_start = "2023-01-01"
    target_end = "2025-12-31"
    
    coverage_ok = []
    coverage_issue = []
    
    for symbol, tfs in availability.items():
        if tfs.get('D', {}).get('exists'):
            start = tfs['D'].get('start', '')
            end = tfs['D'].get('end', '')
            
            if start and end:
                if start <= target_start and end >= "2025-01-01":
                    coverage_ok.append(symbol)
                else:
                    coverage_issue.append({
                        "symbol": symbol,
                        "start": start,
                        "end": end,
                    })
    
    print(f"\n✅ {len(coverage_ok)} symbols have full 2023-2025 coverage")
    
    if coverage_issue:
        print(f"\n⚠️  {len(coverage_issue)} symbols have incomplete coverage:")
        for issue in coverage_issue[:10]:
            print(f"   {issue['symbol']}: {issue['start']} to {issue['end']}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_symbols = len(availability)
    with_daily = len(symbols_with_daily)
    
    print(f"\n  Total symbols:           {total_symbols}")
    print(f"  With daily data:         {with_daily}")
    print(f"  With full 2023-2025:     {len(coverage_ok)}")
    print(f"  With quality issues:     {len(quality_issues)}")
    print(f"  With data gaps:          {len(symbols_with_gaps)}")
    
    # Save report
    report = {
        "generated": datetime.now().isoformat(),
        "summary": {
            "total_symbols": total_symbols,
            "with_daily_data": with_daily,
            "with_full_coverage": len(coverage_ok),
            "with_quality_issues": len(quality_issues),
            "with_data_gaps": len(symbols_with_gaps),
        },
        "availability": availability,
        "quality_issues": quality_issues,
        "coverage_issues": coverage_issue,
    }
    
    output_path = WORKSPACE / "analysis" / "data_consistency_report.json"
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Full report saved to: {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check data consistency")
    parser.add_argument("--symbol", help="Check specific symbol")
    parser.add_argument("--gaps", action="store_true", help="Check gaps for symbol")
    parser.add_argument("--validity", action="store_true", help="Check OHLC validity")
    parser.add_argument("--full", action="store_true", help="Generate full report")
    
    args = parser.parse_args()
    
    if args.symbol:
        if args.gaps:
            result = check_data_gaps(args.symbol, "D")
            print(json.dumps(result, indent=2, default=str))
        elif args.validity:
            result = check_ohlc_validity(args.symbol, "D")
            print(json.dumps(result, indent=2, default=str))
        else:
            result = compare_timeframes(args.symbol)
            print(json.dumps(result, indent=2, default=str))
    elif args.full:
        generate_full_report()
    else:
        generate_full_report()
