#!/bin/bash
# TP/SL Optimizer Runner
# Starts optimizer in background with live logging
# Usage: ./backtest/run_tpsl_optimizer.sh [--trials N] [--start DATE] [--end DATE] [--parallel N]

cd /home/user/20k5ers

TRIALS=${TRIALS:-80}
START=${START:-2015-01-01}
END=${END:-2015-05-31}
PARALLEL=${PARALLEL:-2}
BALANCE=${BALANCE:-20000}
STARTUP=${STARTUP:-10}

# Parse optional args
while [[ $# -gt 0 ]]; do
  case $1 in
    --trials) TRIALS="$2"; shift 2 ;;
    --start)  START="$2";  shift 2 ;;
    --end)    END="$2";    shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    *) shift ;;
  esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="backtest/optimization_results/optimizer_run_${TIMESTAMP}.log"
STATUS_FILE="/tmp/optimizer_status_${TIMESTAMP}.txt"

# Kill any existing optimizer runs
EXISTING=$(pgrep -f "optimize_main_live_bot.py" 2>/dev/null)
if [ -n "$EXISTING" ]; then
  echo "Stopping existing optimizer (PID: $EXISTING)..."
  kill $EXISTING 2>/dev/null
  sleep 2
fi

mkdir -p backtest/optimization_results

echo "======================================================================" | tee "$LOG_FILE"
echo "TP/SL OPTIMIZER STARTING" | tee -a "$LOG_FILE"
echo "  Trials:   $TRIALS" | tee -a "$LOG_FILE"
echo "  Period:   $START to $END" | tee -a "$LOG_FILE"
echo "  Parallel: $PARALLEL workers" | tee -a "$LOG_FILE"
echo "  Log:      $LOG_FILE" | tee -a "$LOG_FILE"
echo "  Status:   $STATUS_FILE" | tee -a "$LOG_FILE"
echo "======================================================================" | tee -a "$LOG_FILE"

# Write status file path so tail -f works from anywhere
echo "$LOG_FILE" > /tmp/optimizer_current_log.txt
echo "$STATUS_FILE" > /tmp/optimizer_current_status.txt

# Run optimizer in background using python -u (unbuffered = constant updates)
nohup python -u backtest/optimize_main_live_bot.py \
  --trials "$TRIALS" \
  --start "$START" \
  --end "$END" \
  --balance "$BALANCE" \
  --parallel "$PARALLEL" \
  --startup-trials "$STARTUP" \
  >> "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > /tmp/optimizer_pid.txt

echo ""
echo "✅ Optimizer gestart (PID: $PID)"
echo ""
echo "Live volgen:    tail -f $LOG_FILE"
echo "Status check:  cat /tmp/optimizer_current_log.txt | xargs tail -20"
echo "Stoppen:       kill $PID"
echo ""
echo "Of monitor script: ./backtest/monitor_optimizer.sh"
