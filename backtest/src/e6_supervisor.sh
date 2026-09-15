#!/usr/bin/env bash
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/e6_run.log
for ((i = 0; i < 300; i++)); do
  while pgrep -f "e6_decade_chunked.py" >/dev/null 2>&1; do sleep 20; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] decade complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/e6_decade_chunked.py \
    --first-start 2015-02-01 >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
