#!/usr/bin/env bash
# Supervisor for the intrabar worst-case re-screen. Liveness is ANCHORED so the
# launching shell (whose command line contains this script's name) cannot match.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/worstcase_run.log
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_worstcase"; }
for ((i = 0; i < 500; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] worstcase complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_worstcase.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
