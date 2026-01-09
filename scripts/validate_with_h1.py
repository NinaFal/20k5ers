#!/usr/bin/env python3
"""
Validate run009 trades with H1 data.

Compares:
- Original D1-based results
- New H1-based results

Trade count MUST stay the same (2008).
Win-rate and profit CAN change.
"""

import json
import pandas as pd
from pathlib import Path
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from tradr.backtest.h1_trade_simulator import simulate_trades_with_h1


def load_trades(run_dir: str) -> pd.DataFrame:
    """Load trades from validation run."""
    run_path = Path(run_dir)
    
    # Find trade file - prioritize final trades
    patterns = [
        'best_trades_final.csv',
        '*trades_final*.csv',
        '*trades*.csv', 
        '*trade*.csv', 
        '*history*.csv'
    ]
    
    for pattern in patterns:
        files = list(run_path.glob(pattern))
        if files:
            df = pd.read_csv(files[0])
            print(f"📄 Loaded {len(df)} trades from {files[0].name}")
            print(f"   Columns: {list(df.columns)}")
            return df
    
    raise FileNotFoundError(f"No trade file found in {run_dir}")


def compare_results(original_df: pd.DataFrame, h1_df: pd.DataFrame) -> dict:
    """Compare original vs H1 results."""
    
    print("\n" + "=" * 70)
    print("COMPARISON: D1-BASED vs H1-BASED")
    print("=" * 70)
    
    comparison = {}
    
    # Trade counts
    print(f"\n📊 TRADE COUNTS:")
    print(f"   Original: {len(original_df)}")
    print(f"   H1-based: {len(h1_df)}")
    
    comparison['original_count'] = len(original_df)
    comparison['h1_count'] = len(h1_df)
    comparison['counts_match'] = len(original_df) == len(h1_df)
    
    if comparison['counts_match']:
        print("   ✅ Match!")
    else:
        print("   ❌ MISMATCH!")
    
    # Win rates
    print(f"\n📊 WIN RATES:")
    
    # Original wins - check multiple column names
    if 'is_winner' in original_df.columns:
        orig_wins = original_df['is_winner'].sum()
    elif 'win' in original_df.columns:
        orig_wins = original_df['win'].sum()
    elif 'result_r' in original_df.columns:
        orig_wins = (original_df['result_r'] > 0).sum()
    else:
        orig_wins = 0
    
    h1_wins = h1_df['is_winner'].sum()
    
    orig_wr = orig_wins / len(original_df) * 100 if len(original_df) > 0 else 0
    h1_wr = h1_wins / len(h1_df) * 100 if len(h1_df) > 0 else 0
    
    print(f"   Original: {orig_wins} wins ({orig_wr:.1f}%)")
    print(f"   H1-based: {h1_wins} wins ({h1_wr:.1f}%)")
    print(f"   Difference: {h1_wr - orig_wr:+.1f}%")
    
    comparison['original_wins'] = int(orig_wins)
    comparison['h1_wins'] = int(h1_wins)
    comparison['original_winrate'] = round(orig_wr, 2)
    comparison['h1_winrate'] = round(h1_wr, 2)
    
    # Total RR
    print(f"\n📊 TOTAL R/R:")
    
    if 'result_r' in original_df.columns:
        orig_rr = original_df['result_r'].sum()
    elif 'rr' in original_df.columns:
        orig_rr = original_df['rr'].sum()
    else:
        orig_rr = 0
    
    h1_rr = h1_df['rr'].sum()
    
    print(f"   Original: {orig_rr:.2f}R")
    print(f"   H1-based: {h1_rr:.2f}R")
    print(f"   Difference: {h1_rr - orig_rr:+.2f}R")
    
    comparison['original_rr'] = round(orig_rr, 2)
    comparison['h1_rr'] = round(h1_rr, 2)
    
    # Average RR per winning trade
    print(f"\n📊 AVG RR (WINNERS):")
    
    if 'result_r' in original_df.columns:
        orig_win_mask = original_df['result_r'] > 0
        orig_avg_win = original_df.loc[orig_win_mask, 'result_r'].mean() if orig_win_mask.any() else 0
    elif 'win' in original_df.columns:
        orig_win_mask = original_df['win'] == 1
        if 'result_r' in original_df.columns:
            orig_avg_win = original_df.loc[orig_win_mask, 'result_r'].mean() if orig_win_mask.any() else 0
        else:
            orig_avg_win = 0
    else:
        orig_avg_win = 0
    
    h1_win_mask = h1_df['is_winner'] == True
    h1_avg_win = h1_df.loc[h1_win_mask, 'rr'].mean() if h1_win_mask.any() else 0
    
    print(f"   Original: {orig_avg_win:.3f}R")
    print(f"   H1-based: {h1_avg_win:.3f}R")
    
    comparison['original_avg_win_rr'] = round(orig_avg_win, 4)
    comparison['h1_avg_win_rr'] = round(h1_avg_win, 4)
    
    # Exit reasons (H1)
    print(f"\n📊 EXIT REASONS (H1):")
    exit_counts = h1_df['exit_reason'].value_counts()
    comparison['exit_reasons'] = {}
    
    for reason, count in exit_counts.items():
        pct = count / len(h1_df) * 100
        print(f"   {reason}: {count} ({pct:.1f}%)")
        comparison['exit_reasons'][reason] = int(count)
    
    # TP hit distribution
    print(f"\n📊 TP HIT DISTRIBUTION (H1):")
    for tp_level in ['tp1', 'tp2', 'tp3']:
        col = f'{tp_level}_hit'
        if col in h1_df.columns:
            hit_count = h1_df[col].sum()
            hit_pct = hit_count / len(h1_df) * 100
            print(f"   {tp_level.upper()}: {hit_count} ({hit_pct:.1f}%)")
            comparison[f'{tp_level}_hit_count'] = int(hit_count)
    
    # Symbol breakdown
    print(f"\n📊 SYMBOL PERFORMANCE (H1):")
    symbol_stats = h1_df.groupby('symbol').agg({
        'rr': ['count', 'sum', 'mean'],
        'is_winner': 'sum'
    }).round(3)
    symbol_stats.columns = ['trades', 'total_rr', 'avg_rr', 'wins']
    symbol_stats['winrate'] = (symbol_stats['wins'] / symbol_stats['trades'] * 100).round(1)
    symbol_stats = symbol_stats.sort_values('total_rr', ascending=False)
    
    print(symbol_stats.head(10).to_string())
    
    comparison['symbol_stats'] = symbol_stats.to_dict()
    
    # Hours in trade stats
    if 'hours_in_trade' in h1_df.columns:
        print(f"\n📊 TIME IN TRADE (H1):")
        avg_hours = h1_df['hours_in_trade'].mean()
        median_hours = h1_df['hours_in_trade'].median()
        max_hours = h1_df['hours_in_trade'].max()
        print(f"   Average: {avg_hours:.1f} hours ({avg_hours/24:.1f} days)")
        print(f"   Median: {median_hours:.1f} hours ({median_hours/24:.1f} days)")
        print(f"   Max: {max_hours} hours ({max_hours/24:.1f} days)")
        
        comparison['avg_hours_in_trade'] = round(avg_hours, 1)
        comparison['median_hours_in_trade'] = round(median_hours, 1)
    
    return comparison


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate trades with H1 data')
    parser.add_argument('--run', type=str,
                       default='ftmo_analysis_output/VALIDATE/history/val_2023_2025_003',
                       help='Validation run directory')
    parser.add_argument('--output', type=str,
                       default='analysis/h1_validation_results.csv')
    parser.add_argument('--h1-dir', type=str,
                       default='data/ohlcv',
                       help='Directory with H1 data files')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("H1 VALIDATION")
    print("=" * 70)
    print(f"Run: {args.run}")
    print(f"H1 data: {args.h1_dir}")
    print(f"Output: {args.output}")
    
    # Load trades
    original_df = load_trades(args.run)
    
    # Simulate with H1
    print(f"\n🔄 Simulating {len(original_df)} trades with H1 data...")
    start_time = datetime.now()
    h1_df = simulate_trades_with_h1(original_df, h1_data_dir=args.h1_dir, progress=True)
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"   Done in {elapsed:.1f}s ({len(original_df)/elapsed:.1f} trades/sec)")
    
    # Compare
    comparison = compare_results(original_df, h1_df)
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    
    h1_df.to_csv(output_path, index=False)
    print(f"\n✅ H1 trades saved to: {output_path}")
    
    # Save comparison JSON
    json_path = output_path.with_suffix('.json')
    with open(json_path, 'w') as f:
        # Convert any non-serializable types
        comparison_serializable = {}
        for k, v in comparison.items():
            if isinstance(v, dict):
                comparison_serializable[k] = {str(kk): (vv.tolist() if hasattr(vv, 'tolist') else vv) 
                                              for kk, vv in v.items()}
            else:
                comparison_serializable[k] = v
        json.dump(comparison_serializable, f, indent=2)
    print(f"✅ Comparison saved to: {json_path}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Trades: {comparison['original_count']} → {comparison['h1_count']}")
    print(f"Win rate: {comparison['original_winrate']:.1f}% → {comparison['h1_winrate']:.1f}%")
    print(f"Total RR: {comparison['original_rr']:.2f}R → {comparison['h1_rr']:.2f}R")
    print(f"Difference: {comparison['h1_rr'] - comparison['original_rr']:+.2f}R")


if __name__ == '__main__':
    main()
