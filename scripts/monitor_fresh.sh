#!/bin/bash
# Monitor fresh 100-trial optimization

echo "=== FRESH 100-TRIAL OPTIMIZATION MONITOR ==="
echo ""

# Check if process is running
if pgrep -f "ftmo_challenge_analyzer.py --trials 100" > /dev/null; then
    PID=$(pgrep -f "ftmo_challenge_analyzer.py --trials 100")
    echo "✓ Optimizer is RUNNING (PID: $PID)"
else
    echo "✗ Optimizer is NOT running"
fi

echo ""
echo "=== RECENT TRIALS (last 10) ==="
grep "TRIAL #" /workspaces/mt5bot-new/ftmo_optimization_fresh.log | tail -10

echo ""
echo "=== CURRENT BEST SCORE ==="
grep "Best:" /workspaces/mt5bot-new/ftmo_optimization_fresh.log | tail -1 || echo "No trades yet"

echo ""
echo "=== PROGRESS ==="
TOTAL=$(grep "TRIAL #" /workspaces/mt5bot-new/ftmo_optimization_fresh.log | wc -l)
echo "Trials completed so far: $TOTAL / 100"

echo ""
echo "To watch live:"
echo "  tail -f /workspaces/mt5bot-new/ftmo_optimization_fresh.log"
