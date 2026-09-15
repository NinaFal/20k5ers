#!/usr/bin/env bash
# Supervisor for S0. The container restarts constantly; S0 caches per start.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/s0_run.log
touch "$LOG"
for ((i = 0; i < 400; i++)); do
  while pgrep -f "s0_speed_anatomy.py" >/dev/null 2>&1; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/s0_speed_anatomy.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
