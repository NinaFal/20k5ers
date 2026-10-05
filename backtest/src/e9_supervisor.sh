#!/usr/bin/env bash
# Supervisor for E9. The container restarts constantly; E9 caches per start, so
# a restart costs at most one start.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/e9_run.log
touch "$LOG"
for ((i = 0; i < 400; i++)); do
  while pgrep -f "e9_random100.py" >/dev/null 2>&1; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/e9_random100.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
