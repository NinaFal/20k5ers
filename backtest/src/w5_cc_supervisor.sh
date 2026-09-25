#!/usr/bin/env bash
# Supervisor for the chunked continuous decade run. Anchored liveness check.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/continuous_chunked_run.log
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_continuous_chunked"; }
for ((i = 0; i < 500; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] chunked continuous complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_continuous_chunked.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
