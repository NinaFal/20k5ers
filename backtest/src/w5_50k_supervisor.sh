#!/usr/bin/env bash
# Supervisor for the $50k 2015-2025 run (scaled + compound arms).
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/fiftyk_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_50k_decade"; }
for ((i = 0; i < 600; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] 50k run complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_50k_decade.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
