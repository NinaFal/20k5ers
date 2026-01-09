#!/usr/bin/env python3
"""
Quick script to run backtests with best parameters and update CSV files.
"""

import sys
import os

# Add project root to path (parent of scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # Change to project root for file paths

import json
from pathlib import Path
from ftmo_challenge_analyzer import (
    run_full_period_backtest, 
    export_trades_to_csv,
    TRAINING_START, TRAINING_END,
    VALIDATION_START, VALIDATION_END,
    FULL_PERIOD_START, FULL_PERIOD_END
)

def main():
    # Load best params
    best_params = json.loads(Path('best_params.json').read_text())
    risk_pct = best_params.get('risk_per_trade_pct', 0.5)
    
    print("=" * 60)
    print("BACKTEST WITH TRIAL #35 (BEST) PARAMETERS")
    print("=" * 60)
    print("\nParameters:")
    for k, v in sorted(best_params.items()):
        print(f"  {k}: {v}")
    
    print(f"\n📊 Running Training Period Backtest (2023-01-01 to 2024-09-30)...")
    training_trades = run_full_period_backtest(
        start_date=TRAINING_START, end_date=TRAINING_END,
        min_confluence=best_params.get('min_confluence_score', 3),
        min_quality_factors=best_params.get('min_quality_factors', 2),
        risk_per_trade_pct=risk_pct,
        atr_min_percentile=best_params.get('atr_min_percentile', 60.0),
        trail_activation_r=best_params.get('trail_activation_r', 2.2),
        volatile_asset_boost=best_params.get('volatile_asset_boost', 1.0),
        require_adx_filter=True,
        adx_trend_threshold=best_params.get('adx_trend_threshold', 25.0),
        adx_range_threshold=best_params.get('adx_range_threshold', 20.0),
        trend_min_confluence=best_params.get('trend_min_confluence', 6),
        range_min_confluence=best_params.get('range_min_confluence', 5),
        atr_volatility_ratio=best_params.get('atr_vol_ratio_range', 0.8),
        atr_trail_multiplier=best_params.get('atr_trail_multiplier', 1.5),
        partial_exit_at_1r=best_params.get('partial_exit_at_1r', True),
    )
    print(f"  Training: {len(training_trades)} trades")
    
    print(f"\n📊 Running Validation Period Backtest (2024-10-01 to 2025-12-26)...")
    validation_trades = run_full_period_backtest(
        start_date=VALIDATION_START, end_date=VALIDATION_END,
        min_confluence=best_params.get('min_confluence_score', 3),
        min_quality_factors=best_params.get('min_quality_factors', 2),
        risk_per_trade_pct=risk_pct,
        atr_min_percentile=best_params.get('atr_min_percentile', 60.0),
        trail_activation_r=best_params.get('trail_activation_r', 2.2),
        volatile_asset_boost=best_params.get('volatile_asset_boost', 1.0),
        require_adx_filter=True,
        adx_trend_threshold=best_params.get('adx_trend_threshold', 25.0),
        adx_range_threshold=best_params.get('adx_range_threshold', 20.0),
        trend_min_confluence=best_params.get('trend_min_confluence', 6),
        range_min_confluence=best_params.get('range_min_confluence', 5),
        atr_volatility_ratio=best_params.get('atr_vol_ratio_range', 0.8),
        atr_trail_multiplier=best_params.get('atr_trail_multiplier', 1.5),
        partial_exit_at_1r=best_params.get('partial_exit_at_1r', True),
    )
    print(f"  Validation: {len(validation_trades)} trades")
    
    print(f"\n📊 Running Full Period Backtest (2023-01-01 to 2025-12-26)...")
    full_trades = run_full_period_backtest(
        start_date=FULL_PERIOD_START, end_date=FULL_PERIOD_END,
        min_confluence=best_params.get('min_confluence_score', 3),
        min_quality_factors=best_params.get('min_quality_factors', 2),
        risk_per_trade_pct=risk_pct,
        atr_min_percentile=best_params.get('atr_min_percentile', 60.0),
        trail_activation_r=best_params.get('trail_activation_r', 2.2),
        volatile_asset_boost=best_params.get('volatile_asset_boost', 1.0),
        require_adx_filter=True,
        adx_trend_threshold=best_params.get('adx_trend_threshold', 25.0),
        adx_range_threshold=best_params.get('adx_range_threshold', 20.0),
        trend_min_confluence=best_params.get('trend_min_confluence', 6),
        range_min_confluence=best_params.get('range_min_confluence', 5),
        atr_volatility_ratio=best_params.get('atr_vol_ratio_range', 0.8),
        atr_trail_multiplier=best_params.get('atr_trail_multiplier', 1.5),
        partial_exit_at_1r=best_params.get('partial_exit_at_1r', True),
    )
    print(f"  Full: {len(full_trades)} trades")
    
    # Export CSVs
    print(f"\n📁 Exporting CSV files...")
    export_trades_to_csv(training_trades, "all_trades_jan_dec_2024.csv", risk_pct)
    export_trades_to_csv(validation_trades, "all_trades_2024_full.csv", risk_pct)
    export_trades_to_csv(full_trades, "all_trades_2023_2025_full.csv", risk_pct)
    print("✅ All CSV files exported!")
    
    # Calculate stats
    def calc_stats(trades):
        if not trades:
            return 0, 0, 0, 0
        total_r = sum(getattr(t, 'rr', 0) for t in trades)
        wins = sum(1 for t in trades if getattr(t, 'rr', 0) > 0)
        win_rate = (wins / len(trades) * 100) if trades else 0
        return len(trades), wins, win_rate, total_r
    
    train_stats = calc_stats(training_trades)
    val_stats = calc_stats(validation_trades)
    full_stats = calc_stats(full_trades)
    
    print(f"\n{'='*60}")
    print("FINAL RESULTS (Trial #35 - Best Score: 66.05)")
    print(f"{'='*60}")
    print(f"\nTraining Period (2023-01 to 2024-09):")
    print(f"  Trades: {train_stats[0]}, Wins: {train_stats[1]}, Win Rate: {train_stats[2]:.1f}%, Total R: {train_stats[3]:.2f}")
    
    print(f"\nValidation Period (2024-10 to 2025-12):")
    print(f"  Trades: {val_stats[0]}, Wins: {val_stats[1]}, Win Rate: {val_stats[2]:.1f}%, Total R: {val_stats[3]:.2f}")
    
    print(f"\nFull Period (2023-01 to 2025-12):")
    print(f"  Trades: {full_stats[0]}, Wins: {full_stats[1]}, Win Rate: {full_stats[2]:.1f}%, Total R: {full_stats[3]:.2f}")
    
    # Calculate profit at 0.3% risk
    account_size = 80000
    risk_usd = account_size * (risk_pct / 100)
    print(f"\n💰 Profit Estimate (${account_size:,} account, {risk_pct}% risk = ${risk_usd:.2f}/trade):")
    print(f"  Training:   ${train_stats[3] * risk_usd:,.2f}")
    print(f"  Validation: ${val_stats[3] * risk_usd:,.2f}")
    print(f"  Full:       ${full_stats[3] * risk_usd:,.2f}")

if __name__ == "__main__":
    main()
