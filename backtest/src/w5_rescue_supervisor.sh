#!/usr/bin/env bash
# Supervisor for the t65 rescue sweep. Anchored liveness check so the shell that
# launched this script cannot match its own command line.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/rescue_t65_run.log
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_rescue_t65"; }
for ((i = 0; i < 500; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] rescue complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_rescue_t65.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
