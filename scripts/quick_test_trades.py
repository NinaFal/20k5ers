#!/usr/bin/env python3
"""Quick test to see if ANY trades are possible with loose settings"""

import sys
import os

# Add project root to path (parent of scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from strategy_core import simulate_trades
import pandas as pd
import os

# Check what data files exist
data_dir = '/workspaces/mt5bot-new/data/ohlcv'
files = os.listdir(data_dir) if os.path.exists(data_dir) else []
print(f"Available data files: {len(files)} files")
if files:
    print(f"Sample: {files[:5]}")

# Load data for ONE asset to test manually
symbol = "AUDUSD"
file_path = f'{data_dir}/{symbol}_D1_2003_2025.csv'
print(f"\nLoading from: {file_path}")

if not os.path.exists(file_path):
    print(f"ERROR: File not found: {file_path}")
    sys.exit(1)

data = pd.read_csv(file_path)
print(f"Loaded {len(data)} rows")
print(f"Columns: {data.columns.tolist()}")

# Limit to training period
if 'time' in data.columns:
    data['time'] = pd.to_datetime(data['time'])
    train_end = pd.to_datetime('2024-09-30')
    data = data[data['time'] <= train_end]
    print(f"Data points for training (2023-01-01 to 2024-09-30): {len(data)}")
    # Rename 'time' to 'timestamp' for compatibility
    data = data.rename(columns={'time': 'timestamp'})
elif 'timestamp' in data.columns:
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    train_end = pd.to_datetime('2024-09-30')
    data = data[data['timestamp'] <= train_end]
    print(f"Data points for training (2023-01-01 to 2024-09-30): {len(data)}")
else:
    print("ERROR: No timestamp or time column")
    sys.exit(1)

# Convert dataframe to candle dicts format
candles = []
for _, row in data.iterrows():
    candle = {
        'time': row['timestamp'],
        'open': float(row['Open']),
        'high': float(row['High']),
        'low': float(row['Low']),
        'close': float(row['Close']),
        'volume': float(row['Volume']) if 'Volume' in row and pd.notna(row['Volume']) else 0,
    }
    candles.append(candle)

print(f"Converted to {len(candles)} candles")

from strategy_core import StrategyParams

# Create params object
params = StrategyParams(
    min_confluence=3,  # MINIMUM confluence
    min_quality_factors=1,
    risk_per_trade_pct=1.0,
    atr_min_percentile=20.0,
    trail_activation_r=1.0,
    volatile_asset_boost=1.0,
    adx_trend_threshold=20.0,
    adx_range_threshold=15.0,
)

print(f"Testing with VERY LOOSE parameters: min_confluence={params.min_confluence}, atr={params.atr_min_percentile}")
print("\nGenerating signals...")

try:
    trades = simulate_trades(
        candles=candles,
        symbol=symbol,
        params=params,
    )
    
    print(f"\n✓ SUCCESS: Generated {len(trades)} trades")
    
except Exception as e:
    print(f"\n✗ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
