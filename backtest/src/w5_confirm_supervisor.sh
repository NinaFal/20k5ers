#!/usr/bin/env bash
# Runs the risk2.2 confirmation after the safety sweep finishes.
cd /home/user/20k5ers || exit 1
SLOG=backtest/output/doe/wall5/safety_sweep_run.log
LOG=backtest/output/doe/wall5/confirm_risk22_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_confirm_risk22"; }
for ((i = 0; i < 600; i++)); do
  grep -q "w5_safety_sweep. DONE_MARKER" "$SLOG" 2>/dev/null && break
  sleep 60
done
for ((i = 0; i < 900; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] confirmation complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_confirm_risk22.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
