#!/bin/bash
# Run 4 parallel backtests for 2023 Q1-Q4

cd /workspaces/20k5ers

echo "Starting 4 parallel backtests for 2023..."

python backtest/src/main_live_bot_backtest.py --start 2023-01-01 --end 2023-03-31 --balance 20000 > backtest/output/2023_Q1_compound.log 2>&1 &
PID1=$!
echo "Q1 started (PID: $PID1)"

python backtest/src/main_live_bot_backtest.py --start 2023-04-01 --end 2023-06-30 --balance 20000 > backtest/output/2023_Q2_compound.log 2>&1 &
PID2=$!
echo "Q2 started (PID: $PID2)"

python backtest/src/main_live_bot_backtest.py --start 2023-07-01 --end 2023-09-30 --balance 20000 > backtest/output/2023_Q3_compound.log 2>&1 &
PID3=$!
echo "Q3 started (PID: $PID3)"

python backtest/src/main_live_bot_backtest.py --start 2023-10-01 --end 2023-12-31 --balance 20000 > backtest/output/2023_Q4_compound.log 2>&1 &
PID4=$!
echo "Q4 started (PID: $PID4)"

echo ""
echo "Waiting for all 4 backtests to complete..."
wait $PID1 $PID2 $PID3 $PID4

echo ""
echo "All backtests complete! Extracting results..."
echo ""
echo "=== Q1 2023 ==="
tail -30 backtest/output/2023_Q1_compound.log | grep -E "(Final|Profit|DDD|Win|Trades|Balance)"

echo ""
echo "=== Q2 2023 ==="
tail -30 backtest/output/2023_Q2_compound.log | grep -E "(Final|Profit|DDD|Win|Trades|Balance)"

echo ""
echo "=== Q3 2023 ==="
tail -30 backtest/output/2023_Q3_compound.log | grep -E "(Final|Profit|DDD|Win|Trades|Balance)"

echo ""
echo "=== Q4 2023 ==="
tail -30 backtest/output/2023_Q4_compound.log | grep -E "(Final|Profit|DDD|Win|Trades|Balance)"
