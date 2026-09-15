#!/usr/bin/env bash
# Supervisor for E7. The container restarts constantly; E7 caches per year, so
# a restart costs at most the year in flight.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/e7_run.log
touch "$LOG"
for ((i = 0; i < 300; i++)); do
  while pgrep -f "e7_yearly_100k.py" >/dev/null 2>&1; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/e7_yearly_100k.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
