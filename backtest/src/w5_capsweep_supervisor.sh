#!/usr/bin/env bash
# Cap sweep runs last: after the scaling probe and the wall-enforcement test,
# so the 100-start holdout keeps its four workers throughout.
cd /home/user/20k5ers || exit 1
WLOG=backtest/output/doe/wall5/wall_enforcement_run.log
LOG=backtest/output/doe/wall5/cap_sweep_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_cap_sweep"; }
for ((i = 0; i < 600; i++)); do
  grep -q "w5_wall_enforcement_test. DONE_MARKER" "$WLOG" 2>/dev/null && break
  sleep 60
done
for ((i = 0; i < 600; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] cap sweep complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_cap_sweep.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
