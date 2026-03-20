#!/bin/bash
# Monitor de lopende TP/SL optimizer
# Usage: ./backtest/monitor_optimizer.sh

PID_FILE="/tmp/optimizer_pid.txt"
LOG_REF="/tmp/optimizer_current_log.txt"

if [ ! -f "$LOG_REF" ]; then
  echo "Geen actieve optimizer gevonden."
  echo "Start met: ./backtest/run_tpsl_optimizer.sh"
  exit 1
fi

LOG_FILE=$(cat "$LOG_REF")

if [ ! -f "$LOG_FILE" ]; then
  echo "Log file niet gevonden: $LOG_FILE"
  exit 1
fi

# Check of het process nog loopt
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if ps -p $PID > /dev/null 2>&1; then
    echo "✅ Optimizer LOOPT (PID: $PID)"
  else
    echo "⏹️  Optimizer KLAAR"
  fi
fi

echo "Log: $LOG_FILE"
echo ""

# Toon beste trial tot nu toe
echo "--- BESTE RESULTATEN TOT NU TOE ---"
grep "Best is trial" "$LOG_FILE" | tail -3 2>/dev/null || echo "(nog geen trials klaar)"
echo ""

echo "--- LAATSTE TRIALS ---"
grep -E "(Trial [0-9]+:|→ Return:)" "$LOG_FILE" | tail -20 2>/dev/null

echo ""
echo "--- LIVE FOLLOW ---"
echo "tail -f $LOG_FILE"
