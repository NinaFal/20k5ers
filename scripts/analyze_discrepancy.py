#!/usr/bin/env python3
"""
SIGNAL DISCREPANCY ANALYZER

For each signal that differs between TPE validate and Live Bot simulation,
this tool digs deep to find EXACTLY why they differ.

Analyzes:
- HTF trend differences
- Confluence flag differences  
- Quality factor differences
- Data availability differences
- Timing/candle differences

Author: AI Assistant
Date: January 5, 2026
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategy_core import (
    compute_confluence,
    _infer_trend,
    _pick_direction_from_bias,
    _slice_htf_by_timestamp,
    StrategyParams,
)
from params.params_loader import load_strategy_params

WORKSPACE = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE / "data" / "ohlcv"


def oanda_to_mt5_symbol(oanda_symbol: str) -> str:
    """Convert OANDA format (EUR_USD) to MT5 format (EURUSD)."""
    special = {
        "XAU_USD": "XAUUSD",
        "XAG_USD": "XAGUSD",
        "BTC_USD": "BTCUSD",
        "ETH_USD": "ETHUSD",
        "NAS100_USD": "NAS100USD",
        "SPX500_USD": "SPX500USD",
    }
    if oanda_symbol in special:
        return special[oanda_symbol]
    return oanda_symbol.replace("_", "")


def load_ohlcv_data(symbol: str, timeframe: str = "D") -> List[Dict]:
    """Load OHLCV data for a symbol and timeframe."""
    mt5_symbol = oanda_to_mt5_symbol(symbol)
    
    tf_map = {
        "M": "MN",
        "W": "W1", 
        "D": "D1",
        "H4": "H4",
        "H1": "H1",
    }
    
    tf_code = tf_map.get(timeframe, timeframe)
    filepath = DATA_DIR / f"{mt5_symbol}_{tf_code}_2003_2025.csv"
    
    if not filepath.exists():
        return []
    
    try:
        df = pd.read_csv(filepath)
        df.columns = df.columns.str.lower()
        
        if 'datetime' in df.columns and 'time' not in df.columns:
            df.rename(columns={'datetime': 'time'}, inplace=True)
        
        candles = df.to_dict('records')
        
        for c in candles:
            if 'time' in c:
                if isinstance(c['time'], str):
                    c['time'] = pd.to_datetime(c['time'])
        
        return candles
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []


def get_candles_up_to_date(candles: List[Dict], target_date: datetime) -> List[Dict]:
    """Get candles up to target_date (no look-ahead)."""
    result = []
    for c in candles:
        candle_time = c.get('time')
        if candle_time is None:
            continue
            
        if isinstance(candle_time, str):
            candle_time = pd.to_datetime(candle_time)
        
        if hasattr(candle_time, 'tzinfo') and candle_time.tzinfo:
            candle_time = candle_time.replace(tzinfo=None)
            
        target_naive = target_date.replace(tzinfo=None) if hasattr(target_date, 'tzinfo') else target_date
        
        if candle_time.date() <= target_naive.date():
            result.append(c)
    
    return result


def analyze_signal_on_date(
    symbol: str,
    date_str: str,
    expected_direction: str,
    params: StrategyParams,
) -> Dict[str, Any]:
    """
    Deeply analyze what signal generation would produce on a specific date.
    
    Returns comprehensive breakdown of all factors.
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Load all data
    daily = load_ohlcv_data(symbol, 'D')
    weekly = load_ohlcv_data(symbol, 'W')
    monthly = load_ohlcv_data(symbol, 'M')
    h4 = load_ohlcv_data(symbol, 'H4')
    
    # Slice to date
    daily_slice = get_candles_up_to_date(daily, date)
    weekly_slice = get_candles_up_to_date(weekly, date)
    monthly_slice = get_candles_up_to_date(monthly, date)
    h4_slice = get_candles_up_to_date(h4, date)
    
    result = {
        "symbol": symbol,
        "date": date_str,
        "expected_direction": expected_direction,
        "data_availability": {
            "daily": len(daily_slice),
            "weekly": len(weekly_slice),
            "monthly": len(monthly_slice),
            "h4": len(h4_slice),
        },
    }
    
    # Check data sufficiency
    if len(daily_slice) < 50:
        result["status"] = "INSUFFICIENT_DAILY_DATA"
        result["reason"] = f"Only {len(daily_slice)} daily candles (need 50+)"
        return result
    
    if len(weekly_slice) < 10:
        result["status"] = "INSUFFICIENT_WEEKLY_DATA"
        result["reason"] = f"Only {len(weekly_slice)} weekly candles (need 10+)"
        return result
    
    # HTF trends
    mn_trend = _infer_trend(monthly_slice) if monthly_slice else "mixed"
    wk_trend = _infer_trend(weekly_slice) if weekly_slice else "mixed"
    d_trend = _infer_trend(daily_slice) if daily_slice else "mixed"
    
    result["htf_trends"] = {
        "monthly": mn_trend,
        "weekly": wk_trend,
        "daily": d_trend,
    }
    
    # Direction from bias
    direction, _, _ = _pick_direction_from_bias(mn_trend, wk_trend, d_trend)
    result["computed_direction"] = direction
    result["direction_match"] = direction == expected_direction
    
    # Compute confluence
    flags, notes, trade_levels = compute_confluence(
        monthly_slice,
        weekly_slice,
        daily_slice,
        h4_slice if h4_slice else daily_slice[-20:],
        direction,
        params,
        historical_sr=None,
    )
    
    entry, sl, tp1, tp2, tp3, tp4, tp5 = trade_levels
    
    confluence_score = sum(1 for v in flags.values() if v)
    
    # Quality factors
    has_location = flags.get("location", False)
    has_fib = flags.get("fib", False)
    has_liquidity = flags.get("liquidity", False)
    has_structure = flags.get("structure", False)
    has_htf_bias = flags.get("htf_bias", False)
    quality_factors = sum([has_location, has_fib, has_liquidity, has_structure, has_htf_bias])
    
    result["confluence"] = {
        "score": confluence_score,
        "required": params.min_confluence,
        "passes": confluence_score >= params.min_confluence,
    }
    
    result["quality"] = {
        "score": quality_factors,
        "required": params.min_quality_factors,
        "passes": quality_factors >= params.min_quality_factors,
    }
    
    result["flags"] = {k: ("✅" if v else "❌") for k, v in flags.items()}
    result["notes"] = notes
    
    result["trade_levels"] = {
        "entry": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "tp4": tp4,
        "tp5": tp5,
    }
    
    # Determine overall status
    if confluence_score >= params.min_confluence and quality_factors >= params.min_quality_factors:
        result["status"] = "ACTIVE"
    elif confluence_score >= params.min_confluence:
        result["status"] = "WATCHING"
    else:
        result["status"] = "SCAN_ONLY"
    
    # Last few candles for context
    if daily_slice:
        last_candle = daily_slice[-1]
        result["last_daily_candle"] = {
            "time": str(last_candle.get('time', '')),
            "open": last_candle.get('open'),
            "high": last_candle.get('high'),
            "low": last_candle.get('low'),
            "close": last_candle.get('close'),
        }
    
    return result


def analyze_discrepancy(
    date_str: str,
    symbol: str,
    expected_direction: str,
    source: str,  # "TPE" or "LIVE"
) -> None:
    """
    Analyze why a signal exists in one system but not the other.
    """
    print("=" * 70)
    print(f"DISCREPANCY ANALYSIS")
    print("=" * 70)
    print(f"\nSignal only in: {source}")
    print(f"Date:           {date_str}")
    print(f"Symbol:         {symbol}")
    print(f"Direction:      {expected_direction}")
    
    params = load_strategy_params()
    print(f"\nParameters:")
    print(f"  min_confluence:      {params.min_confluence}")
    print(f"  min_quality_factors: {params.min_quality_factors}")
    
    result = analyze_signal_on_date(symbol, date_str, expected_direction, params)
    
    print(f"\n" + "-" * 70)
    print("DATA AVAILABILITY")
    print("-" * 70)
    for tf, count in result["data_availability"].items():
        status = "✅" if count >= (50 if tf == "daily" else 10 if tf == "weekly" else 1) else "❌"
        print(f"  {tf:10}: {count:>4} candles {status}")
    
    if "status" in result and result["status"] in ["INSUFFICIENT_DAILY_DATA", "INSUFFICIENT_WEEKLY_DATA"]:
        print(f"\n❌ REASON: {result['reason']}")
        return
    
    print(f"\n" + "-" * 70)
    print("HTF TRENDS")
    print("-" * 70)
    for tf, trend in result["htf_trends"].items():
        print(f"  {tf:10}: {trend}")
    
    print(f"\n  Computed direction: {result['computed_direction']}")
    print(f"  Expected direction: {expected_direction}")
    match_status = "✅ MATCH" if result["direction_match"] else "❌ MISMATCH"
    print(f"  Status:            {match_status}")
    
    print(f"\n" + "-" * 70)
    print("CONFLUENCE FLAGS")
    print("-" * 70)
    for flag, status in result["flags"].items():
        note = result["notes"].get(flag, "")[:40]
        print(f"  {status} {flag:15}: {note}")
    
    conf = result["confluence"]
    qual = result["quality"]
    
    print(f"\n  Confluence: {conf['score']}/{conf['required']} {'✅ PASS' if conf['passes'] else '❌ FAIL'}")
    print(f"  Quality:    {qual['score']}/{qual['required']} {'✅ PASS' if qual['passes'] else '❌ FAIL'}")
    
    print(f"\n" + "-" * 70)
    print("FINAL STATUS")
    print("-" * 70)
    print(f"  {result['status']}")
    
    if result["status"] != "ACTIVE":
        print(f"\n  ⚠️  WHY NOT ACTIVE:")
        if not conf['passes']:
            print(f"      - Confluence too low ({conf['score']} < {conf['required']})")
        if not qual['passes']:
            print(f"      - Quality factors too low ({qual['score']} < {qual['required']})")
        if not result["direction_match"]:
            print(f"      - Direction mismatch (computed {result['computed_direction']}, expected {expected_direction})")
    
    print(f"\n" + "-" * 70)
    print("TRADE LEVELS")
    print("-" * 70)
    levels = result["trade_levels"]
    print(f"  Entry: {levels['entry']}")
    print(f"  SL:    {levels['stop_loss']}")
    print(f"  TP1:   {levels['tp1']}")
    print(f"  TP2:   {levels['tp2']}")
    print(f"  TP3:   {levels['tp3']}")
    print(f"  TP4:   {levels['tp4']}")
    print(f"  TP5:   {levels['tp5']}")
    
    if "last_daily_candle" in result:
        print(f"\n" + "-" * 70)
        print("LAST DAILY CANDLE")
        print("-" * 70)
        c = result["last_daily_candle"]
        print(f"  Time:  {c['time']}")
        print(f"  OHLC:  {c['open']:.5f} / {c['high']:.5f} / {c['low']:.5f} / {c['close']:.5f}")


def compare_both_directions(date_str: str, symbol: str) -> None:
    """
    Compare what both bullish and bearish would produce on a date.
    """
    print("=" * 70)
    print(f"DUAL DIRECTION ANALYSIS: {symbol} on {date_str}")
    print("=" * 70)
    
    params = load_strategy_params()
    
    for direction in ["bullish", "bearish"]:
        print(f"\n{'='*35}")
        print(f"Direction: {direction.upper()}")
        print(f"{'='*35}")
        
        result = analyze_signal_on_date(symbol, date_str, direction, params)
        
        if "status" in result and "INSUFFICIENT" in result.get("status", ""):
            print(f"  ❌ {result['reason']}")
            continue
        
        print(f"\n  HTF Trends: M={result['htf_trends']['monthly']}, W={result['htf_trends']['weekly']}, D={result['htf_trends']['daily']}")
        print(f"  Computed direction: {result['computed_direction']}")
        print(f"\n  Confluence: {result['confluence']['score']}/{result['confluence']['required']} {'✅' if result['confluence']['passes'] else '❌'}")
        print(f"  Quality:    {result['quality']['score']}/{result['quality']['required']} {'✅' if result['quality']['passes'] else '❌'}")
        print(f"\n  Status: {result['status']}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze signal discrepancies")
    parser.add_argument("--date", required=True, help="Date to analyze (YYYY-MM-DD)")
    parser.add_argument("--symbol", required=True, help="Symbol to analyze (e.g., EUR_USD)")
    parser.add_argument("--direction", help="Expected direction (bullish/bearish)")
    parser.add_argument("--source", default="TPE", help="Which system had the signal (TPE or LIVE)")
    parser.add_argument("--both", action="store_true", help="Analyze both directions")
    
    args = parser.parse_args()
    
    if args.both:
        compare_both_directions(args.date, args.symbol)
    elif args.direction:
        analyze_discrepancy(args.date, args.symbol, args.direction, args.source)
    else:
        print("ERROR: Specify --direction or --both")
