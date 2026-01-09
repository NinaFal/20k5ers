#!/bin/bash
# Monitor FTMO optimization progress

echo "=== FTMO OPTIMIZATION MONITOR ==="
echo ""

# Check if process is running
if pgrep -f "ftmo_challenge_analyzer.py --trials 100" > /dev/null; then
    echo "✓ Optimizer is RUNNING (PID: $(pgrep -f 'ftmo_challenge_analyzer.py --trials 100'))"
else
    echo "✗ Optimizer is NOT running"
fi

echo ""
echo "=== RECENT OUTPUT (last 20 lines) ==="
tail -20 /workspaces/mt5bot-new/ftmo_optimization.log

echo ""
echo "=== TRIAL PROGRESS ==="
grep "TRIAL #" /workspaces/mt5bot-new/ftmo_optimization.log | tail -5

echo ""
echo "=== BEST SCORE SO FAR ==="
grep "Best:" /workspaces/mt5bot-new/ftmo_optimization.log | tail -1

echo ""
echo "To watch in real-time, run:"
echo "  tail -f /workspaces/mt5bot-new/ftmo_optimization.log"
