#!/bin/bash

# Monitor backtest progress
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║ BACKTEST MONITORING (2023-2025)                                           ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# Check if process running
if ps aux | grep -v grep | grep "main_live_bot_backtest" > /dev/null; then
  echo "✅ Backtest RUNNING"
else
  echo "⏹️ Backtest FINISHED"
fi

echo ""
echo "Log file: backtest/results/backtest_2023_2025.log"
echo "Output: backtest/results/backtest_2023_2025.json"
echo ""

# Show latest progress
echo "Latest progress bar:"
tail -5 /workspaces/20k5ers/backtest/results/backtest_2023_2025.log 2>/dev/null | grep -i "backtest" || echo "Scanning..."
echo ""

# Count trades if JSON is being written
if [ -f "/workspaces/20k5ers/backtest/results/backtest_2023_2025.json" ]; then
  echo "Results file started: $(ls -lh /workspaces/20k5ers/backtest/results/backtest_2023_2025.json | awk '{print $5}')"
fi

echo ""
echo "Monitor with: tail -f backtest/results/backtest_2023_2025.log"
