#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/stalls_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_stalls_resolved"; }
for ((i = 0; i < 600; i++)); do
  grep -q "w5_holdout2. DONE_MARKER" backtest/output/doe/wall5/holdout2_run.log 2>/dev/null && break
  sleep 30
done
for ((i = 0; i < 600; i++)); do
  while running; do sleep 20; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] stalls complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_stalls_resolved.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
