#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/costs_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_costs"; }
for ((i = 0; i < 900; i++)); do
  while running; do sleep 25; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] costs complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_costs.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
