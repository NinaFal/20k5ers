#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/ladder5_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_stage.py --stage ladder5"; }
for ((i = 0; i < 900; i++)); do
  while running; do sleep 20; done
  grep -q "DONE_MARKER\|\[stage\] done" "$LOG" 2>/dev/null && { echo "[SUP] ladder5 complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_stage.py --stage ladder5 --trials 120 --screen 25 >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
