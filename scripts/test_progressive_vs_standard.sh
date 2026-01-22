#!/bin/bash
# Test progressive trailing vs standard trailing

echo "=========================================================================="
echo "PROGRESSIVE TRAILING STOP TEST"
echo "=========================================================================="
echo ""
echo "Running TWO backtests (2023-2025):"
echo "  1. STANDARD: SL stays at BE between TP1-TP2"
echo "  2. PROGRESSIVE: At 0.9R, SL moves to TP1 (0.6R)"
echo ""
echo "=========================================================================="
echo ""

# Run standard version
echo "🔵 Running STANDARD trailing stop..."
python scripts/backtest_main_live_bot.py \
    --start 2023-01-01 \
    --end 2025-12-31 \
    --balance 20000 \
    --output ftmo_analysis_output/backtest_STANDARD \
    > /tmp/standard.log 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Standard completed"
    STANDARD_RESULT=$(tail -50 /tmp/standard.log | grep -A 10 "FINAL RESULTS")
else
    echo "❌ Standard failed - check /tmp/standard.log"
fi

echo ""
echo "=========================================================================="
echo ""

# Run progressive version
echo "🟢 Running PROGRESSIVE trailing stop..."
python scripts/backtest_main_live_bot.py \
    --start 2023-01-01 \
    --end 2025-12-31 \
    --balance 20000 \
    --progressive-trailing \
    --output ftmo_analysis_output/backtest_PROGRESSIVE \
    > /tmp/progressive.log 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Progressive completed"
    PROGRESSIVE_RESULT=$(tail -50 /tmp/progressive.log | grep -A 10 "FINAL RESULTS")
else
    echo "❌ Progressive failed - check /tmp/progressive.log"
fi

echo ""
echo "=========================================================================="
echo "COMPARISON"
echo "=========================================================================="
echo ""
echo "📊 STANDARD TRAILING:"
tail -50 /tmp/standard.log | grep -E "(Final Balance|Net Return|Total Trades|Win Rate|Max.*DD)"
echo ""
echo "📊 PROGRESSIVE TRAILING:"
tail -50 /tmp/progressive.log | grep -E "(Final Balance|Net Return|Total Trades|Win Rate|Max.*DD)"
echo ""
echo "=========================================================================="
echo ""
echo "Full logs:"
echo "  Standard: /tmp/standard.log"
echo "  Progressive: /tmp/progressive.log"
echo ""
echo "Results saved to:"
echo "  ftmo_analysis_output/backtest_STANDARD/"
echo "  ftmo_analysis_output/backtest_PROGRESSIVE/"
