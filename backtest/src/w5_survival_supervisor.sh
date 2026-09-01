#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/survival_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_survival"; }
for ((i = 0; i < 2000; i++)); do
  while running; do sleep 30; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] survival complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_survival.py --trials 80 >>"$LOG" 2>&1 </dev/null &
  sleep 20
done
