#!/usr/bin/env bash
# Runs the daily-wall enforcement test after the scaling probe finishes, so the
# 100-start holdout keeps its four workers.
cd /home/user/20k5ers || exit 1
PLOG=backtest/output/doe/wall5/scaling_probe_run.log
LOG=backtest/output/doe/wall5/wall_enforcement_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_wall_enforcement_test"; }
for ((i = 0; i < 480; i++)); do
  grep -q "w5_scaling_dd_probe. DONE_MARKER" "$PLOG" 2>/dev/null && break
  sleep 60
done
for ((i = 0; i < 300; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] wall test complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_wall_enforcement_test.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
