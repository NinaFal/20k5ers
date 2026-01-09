#!/usr/bin/env python3
"""
EQUIVALENCE TEST v2: Trade-Level Comparison

Compares ACTUAL TRADES (not just signals) between:
1. TPE validate (trades where entry was achieved)
2. Main live bot simulation (trades that WOULD have filled)

KEY DIFFERENCES FROM v1:
- Uses simulate_trades() which includes entry validation
- Only counts trades where entry price was actually reached
- Matches the exact behavior of TPE validate

Author: AI Assistant
Date: January 5, 2026
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
import pandas as pd
import json
from multiprocessing import Pool
from functools import partial

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategy_core import (
    simulate_trades,
    StrategyParams,
    Trade,
)
from params.params_loader import load_strategy_params

# Constants
WORKSPACE = Path(__file__).resolve().parent.parent
TPE_TRADES_PATH = WORKSPACE / "ftmo_analysis_output" / "VALIDATE" / "best_trades_final.csv"
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


def mt5_to_oanda_symbol(mt5_symbol: str) -> str:
    """Convert MT5 format (EURUSD) to OANDA format (EUR_USD)."""
    special = {
        "XAUUSD": "XAU_USD",
        "XAGUSD": "XAG_USD",
        "BTCUSD": "BTC_USD",
        "ETHUSD": "ETH_USD",
        "NAS100USD": "NAS100_USD",
        "SPX500USD": "SPX500_USD",
    }
    if mt5_symbol in special:
        return special[mt5_symbol]
    if len(mt5_symbol) == 6:
        return mt5_symbol[:3] + "_" + mt5_symbol[3:]
    return mt5_symbol


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


def filter_candles_by_date(candles: List[Dict], start_date: datetime, end_date: datetime) -> List[Dict]:
    """Filter candles to only include those within date range."""
    result = []
    for c in candles:
        candle_time = c.get('time')
        if candle_time is None:
            continue
            
        if isinstance(candle_time, str):
            candle_time = pd.to_datetime(candle_time)
        
        if hasattr(candle_time, 'tzinfo') and candle_time.tzinfo:
            candle_time = candle_time.replace(tzinfo=None)
        
        # Include all candles up to end_date (we need historical context)
        if candle_time.date() <= end_date.date():
            result.append(c)
    
    return result


def get_available_symbols() -> List[str]:
    """Get list of symbols with available data (returns OANDA format)."""
    symbols = set()
    for f in DATA_DIR.glob("*_D1_2003_2025.csv"):
        name = f.stem
        mt5_symbol = name.split("_D1_")[0]
        oanda_symbol = mt5_to_oanda_symbol(mt5_symbol)
        symbols.add(oanda_symbol)
    return sorted(symbols)


@dataclass
class TradeKey:
    """Unique identifier for a trade."""
    date: str  # YYYY-MM-DD
    symbol: str
    direction: str
    
    def __hash__(self):
        return hash((self.date, self.symbol, self.direction))
    
    def __eq__(self, other):
        return (self.date, self.symbol, self.direction) == (other.date, other.symbol, other.direction)


def load_tpe_trades(start_date: str, end_date: str) -> Tuple[pd.DataFrame, Set[TradeKey], Dict[TradeKey, Dict]]:
    """Load TPE validate trades from CSV and filter by date range."""
    if not TPE_TRADES_PATH.exists():
        print(f"ERROR: TPE trades file not found: {TPE_TRADES_PATH}")
        sys.exit(1)
    
    df = pd.read_csv(TPE_TRADES_PATH)
    df['entry_date_parsed'] = pd.to_datetime(df['entry_date'], utc=True)
    df['date_only'] = df['entry_date_parsed'].dt.strftime('%Y-%m-%d')
    
    # Filter by date range (make timezone-aware)
    start_dt = pd.to_datetime(start_date).tz_localize('UTC')
    end_dt = pd.to_datetime(end_date).tz_localize('UTC') + pd.Timedelta(days=1)
    df = df[(df['entry_date_parsed'] >= start_dt) & (df['entry_date_parsed'] < end_dt)]
    
    print(f"Loaded {len(df)} TPE validate trades in date range")
    
    # Build trade set
    trade_keys: Set[TradeKey] = set()
    trade_details: Dict[TradeKey, Dict] = {}
    
    for _, row in df.iterrows():
        key = TradeKey(
            date=row['date_only'],
            symbol=row['symbol'],
            direction=row['direction'],
        )
        trade_keys.add(key)
        trade_details[key] = {
            'entry_price': row['entry_price'],
            'stop_loss': row['stop_loss'],
            'confluence_score': row.get('confluence_score', 0),
            'quality_factors': row.get('quality_factors', 0),
            'result_r': row.get('result_r', 0),
        }
    
    return df, trade_keys, trade_details


def simulate_trades_for_symbol(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    params: StrategyParams,
) -> Tuple[str, List[Trade]]:
    """
    Run simulate_trades() for a symbol and return trades within date range.
    
    This uses the EXACT same logic as TPE validate.
    Returns tuple of (symbol, trades) for parallel processing.
    """
    # Load all data
    daily = load_ohlcv_data(symbol, 'D')
    weekly = load_ohlcv_data(symbol, 'W')
    monthly = load_ohlcv_data(symbol, 'M')
    h4 = load_ohlcv_data(symbol, 'H4')
    
    if len(daily) < 100:
        return (symbol, [])
    
    # Filter to date range (but keep history for indicators)
    daily_filtered = filter_candles_by_date(daily, datetime(2003, 1, 1), end_date)
    weekly_filtered = filter_candles_by_date(weekly, datetime(2003, 1, 1), end_date)
    monthly_filtered = filter_candles_by_date(monthly, datetime(2003, 1, 1), end_date)
    h4_filtered = filter_candles_by_date(h4, datetime(2003, 1, 1), end_date)
    
    if len(daily_filtered) < 50:
        return (symbol, [])
    
    # Run simulate_trades - this handles:
    # 1. Signal generation with confluence/quality checks
    # 2. Entry validation (price must reach entry level)
    # 3. Trade execution and exit logic
    try:
        trades = simulate_trades(
            candles=daily_filtered,
            symbol=symbol,
            params=params,
            monthly_candles=monthly_filtered,
            weekly_candles=weekly_filtered,
            h4_candles=h4_filtered,
            include_transaction_costs=False,  # Match TPE validate
        )
    except Exception as e:
        print(f"  Error simulating {symbol}: {e}")
        return (symbol, [])
    
    # Filter trades to only those with entry_date in our range
    filtered_trades = []
    for trade in trades:
        entry_dt = trade.entry_date
        if isinstance(entry_dt, str):
            try:
                entry_dt = datetime.fromisoformat(entry_dt.replace("Z", "+00:00"))
            except:
                continue
        
        if hasattr(entry_dt, 'tzinfo') and entry_dt.tzinfo:
            entry_dt = entry_dt.replace(tzinfo=None)
        
        if start_date <= entry_dt <= end_date:
            filtered_trades.append(trade)
    
    return (symbol, filtered_trades)


def _simulate_wrapper(args: Tuple[str, datetime, datetime, StrategyParams]) -> Tuple[str, List[Trade]]:
    """Wrapper for multiprocessing - unpacks args tuple."""
    symbol, start_date, end_date, params = args
    return simulate_trades_for_symbol(symbol, start_date, end_date, params)


def run_equivalence_test(
    start_date: str = "2023-01-01",
    end_date: str = "2025-12-31",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Run the trade-level equivalence test.
    
    Uses simulate_trades() to generate trades with entry validation,
    matching the exact behavior of TPE validate.
    """
    print("=" * 70)
    print("EQUIVALENCE TEST v2: Trade-Level Comparison")
    print("=" * 70)
    print(f"\nPeriod: {start_date} to {end_date}")
    
    # Load parameters
    params = load_strategy_params()
    print(f"\nParameters loaded:")
    print(f"  - min_confluence: {params.min_confluence}")
    print(f"  - min_quality_factors: {params.min_quality_factors}")
    print(f"  - risk_per_trade_pct: {params.risk_per_trade_pct}")
    
    # Parse dates
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # Load TPE trades
    tpe_df, tpe_trade_keys, tpe_trade_details = load_tpe_trades(start_date, end_date)
    print(f"\nTPE trades (unique keys): {len(tpe_trade_keys)}")
    
    # Get available symbols
    available_symbols = get_available_symbols()
    tpe_symbols = tpe_df['symbol'].unique().tolist()
    common_symbols = [s for s in tpe_symbols if s in available_symbols]
    
    print(f"Available symbols in data: {len(available_symbols)}")
    print(f"Symbols in TPE trades: {len(tpe_symbols)}")
    print(f"Common symbols (testable): {len(common_symbols)}")
    
    if not common_symbols:
        print("\nERROR: No common symbols found!")
        return {"error": "No common symbols"}
    
    # Simulate trades for each symbol using parallel processing
    print("\n" + "-" * 70)
    print("Simulating trades using simulate_trades()...")
    print("(This uses EXACT same logic as TPE validate)")
    
    num_cores = min(8, os.cpu_count() or 4)
    print(f"Using parallel processing ({num_cores} cores)...\n")
    
    simulated_trade_keys: Set[TradeKey] = set()
    simulated_trade_details: Dict[TradeKey, Dict] = {}
    total_simulated = 0
    
    # Prepare args for parallel processing
    args_list = [(symbol, start_dt, end_dt, params) for symbol in common_symbols]
    
    # Run in parallel
    with Pool(num_cores) as pool:
        results = pool.map(_simulate_wrapper, args_list)
    
    # Process results
    for symbol, trades in results:
        if verbose:
            print(f"  {symbol}: {len(trades)} trades")
        total_simulated += len(trades)
        
        for trade in trades:
            entry_dt = trade.entry_date
            if isinstance(entry_dt, str):
                entry_dt = datetime.fromisoformat(entry_dt.replace("Z", "+00:00"))
            if hasattr(entry_dt, 'tzinfo') and entry_dt.tzinfo:
                entry_dt = entry_dt.replace(tzinfo=None)
            
            date_str = entry_dt.strftime("%Y-%m-%d")
            
            key = TradeKey(
                date=date_str,
                symbol=symbol,
                direction=trade.direction,
            )
            simulated_trade_keys.add(key)
            simulated_trade_details[key] = {
                'entry_price': trade.entry_price,
                'stop_loss': trade.stop_loss,
                'confluence_score': trade.confluence_score,
                'result_r': trade.rr,
            }
    
    print(f"\nTotal simulated trades: {total_simulated}")
    print(f"Unique trade keys: {len(simulated_trade_keys)}")
    
    # Compare
    print("\n" + "=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)
    
    only_in_tpe = tpe_trade_keys - simulated_trade_keys
    only_in_sim = simulated_trade_keys - tpe_trade_keys
    in_both = tpe_trade_keys & simulated_trade_keys
    
    match_rate = len(in_both) / len(tpe_trade_keys) * 100 if tpe_trade_keys else 0
    
    print(f"\n✅ Trades in BOTH:           {len(in_both):>6}")
    print(f"❌ Only in TPE validate:     {len(only_in_tpe):>6}")
    print(f"❌ Only in Simulation:       {len(only_in_sim):>6}")
    print(f"\n📊 Match Rate:               {match_rate:.1f}%")
    
    # Analyze discrepancies
    if only_in_tpe:
        print(f"\n⚠️  TRADES ONLY IN TPE VALIDATE (first 10):")
        for key in list(only_in_tpe)[:10]:
            details = tpe_trade_details.get(key, {})
            print(f"   {key.date} | {key.symbol:12} | {key.direction:7} | Entry: {details.get('entry_price', 0):.5f}")
    
    if only_in_sim:
        print(f"\n⚠️  TRADES ONLY IN SIMULATION (first 10):")
        for key in list(only_in_sim)[:10]:
            details = simulated_trade_details.get(key, {})
            print(f"   {key.date} | {key.symbol:12} | {key.direction:7} | Entry: {details.get('entry_price', 0):.5f}")
    
    # Detailed comparison for matched trades
    if in_both:
        print(f"\n🔍 DETAILED COMPARISON (first 5 matched):")
        entry_diffs = []
        sl_diffs = []
        
        for key in list(in_both)[:5]:
            tpe_detail = tpe_trade_details.get(key, {})
            sim_detail = simulated_trade_details.get(key, {})
            
            entry_diff = abs(tpe_detail.get('entry_price', 0) - sim_detail.get('entry_price', 0))
            sl_diff = abs(tpe_detail.get('stop_loss', 0) - sim_detail.get('stop_loss', 0))
            entry_diffs.append(entry_diff)
            sl_diffs.append(sl_diff)
            
            print(f"\n   {key.date} {key.symbol} {key.direction}:")
            print(f"     Entry:  TPE={tpe_detail.get('entry_price', 0):.5f}, Sim={sim_detail.get('entry_price', 0):.5f}, Diff={entry_diff:.5f}")
            print(f"     SL:     TPE={tpe_detail.get('stop_loss', 0):.5f}, Sim={sim_detail.get('stop_loss', 0):.5f}, Diff={sl_diff:.5f}")
        
        # Check all matched trades for price differences
        all_entry_diffs = []
        all_sl_diffs = []
        for key in in_both:
            tpe_d = tpe_trade_details.get(key, {})
            sim_d = simulated_trade_details.get(key, {})
            all_entry_diffs.append(abs(tpe_d.get('entry_price', 0) - sim_d.get('entry_price', 0)))
            all_sl_diffs.append(abs(tpe_d.get('stop_loss', 0) - sim_d.get('stop_loss', 0)))
        
        if all_entry_diffs:
            print(f"\n📊 PRICE COMPARISON (all {len(in_both)} matched trades):")
            print(f"   Entry price avg diff: {sum(all_entry_diffs)/len(all_entry_diffs):.5f}")
            print(f"   Entry price max diff: {max(all_entry_diffs):.5f}")
            print(f"   SL price avg diff:    {sum(all_sl_diffs)/len(all_sl_diffs):.5f}")
            print(f"   SL price max diff:    {max(all_sl_diffs):.5f}")
    
    # Verdict
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    if match_rate >= 95:
        verdict = "✅ EQUIVALENT - Simulation matches TPE validate"
    elif match_rate >= 85:
        verdict = "⚠️ MOSTLY EQUIVALENT - Minor differences exist"
    elif match_rate >= 70:
        verdict = "⚠️ PARTIAL MATCH - Some differences, investigate discrepancies"
    else:
        verdict = "❌ NOT EQUIVALENT - Major discrepancies between systems"
    
    print(f"\n{verdict}")
    
    # Analyze root causes of differences
    if only_in_tpe or only_in_sim:
        print("\n" + "-" * 70)
        print("ROOT CAUSE ANALYSIS")
        print("-" * 70)
        
        # Weekend trades in TPE
        weekend_tpe = sum(1 for k in only_in_tpe 
                         if datetime.strptime(k.date, "%Y-%m-%d").weekday() >= 5)
        if weekend_tpe > 0:
            print(f"\n  📅 Weekend trades in TPE (not in sim): {weekend_tpe}")
        
        # Symbol coverage issues
        missing_symbols = set(k.symbol for k in only_in_tpe) - set(k.symbol for k in simulated_trade_keys)
        if missing_symbols:
            print(f"\n  🔍 Symbols with TPE trades but no simulation data: {missing_symbols}")
    
    print()
    
    # Build result
    result = {
        "match_rate": match_rate,
        "tpe_trades": len(tpe_trade_keys),
        "simulated_trades": len(simulated_trade_keys),
        "in_both": len(in_both),
        "only_in_tpe": len(only_in_tpe),
        "only_in_sim": len(only_in_sim),
        "verdict": verdict,
        "discrepancies_tpe_only": [
            {"date": k.date, "symbol": k.symbol, "direction": k.direction}
            for k in list(only_in_tpe)[:100]
        ],
        "discrepancies_sim_only": [
            {"date": k.date, "symbol": k.symbol, "direction": k.direction}
            for k in list(only_in_sim)[:100]
        ],
    }
    
    # Save results
    output_path = WORKSPACE / "analysis" / "equivalence_test_v2_results.json"
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Results saved to: {output_path}")
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test trade-level equivalence between simulation and TPE validate")
    parser.add_argument("--start", default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    run_equivalence_test(
        start_date=args.start,
        end_date=args.end,
        verbose=args.verbose,
    )
