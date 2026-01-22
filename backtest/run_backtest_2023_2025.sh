#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST RUNNER - 2023-2025 FULL BACKTEST
# ═══════════════════════════════════════════════════════════════════════════════

set -e

echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║ Running Full Backtest: 2023-01-01 → 2025-12-31                           ║"
echo "║ Initial Balance: $20,000                                                  ║"
echo "║ Data: M15 candles from data/ohlcv/                                        ║"
echo "║ Output: backtest/results/                                                ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# Navigate to project root
cd /workspaces/20k5ers

# Run backtest
python backtest/src/main_live_bot_backtest.py \
  --start 2023-01-01 \
  --end 2025-12-31 \
  --balance 20000 \
  --output backtest/results/backtest_2023_2025.json

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║ BACKTEST COMPLETE ✓                                                       ║"
echo "║ Results saved to: backtest/results/backtest_2023_2025.json                ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"

# Show summary
if [ -f "backtest/results/backtest_2023_2025.json" ]; then
  echo ""
  echo "SUMMARY:"
  python -m json.tool "backtest/results/backtest_2023_2025.json" | head -30
fi
