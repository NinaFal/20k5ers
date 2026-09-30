#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/safety_sweep_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_safety_sweep"; }
for ((i = 0; i < 900; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] sweep complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_safety_sweep.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
