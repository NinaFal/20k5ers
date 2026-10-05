#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/holdout2_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_holdout2"; }
for ((i = 0; i < 900; i++)); do
  while running; do sleep 20; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] holdout2 complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_holdout2.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
