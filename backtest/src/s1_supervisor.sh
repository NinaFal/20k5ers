#!/usr/bin/env bash
# Supervisor for S1. The container restarts constantly; the Optuna study is
# resumable, so a restart costs at most the trial in flight.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/s1_run.log
touch "$LOG"
for ((i = 0; i < 400; i++)); do
  while pgrep -f "s1_ladder.py" >/dev/null 2>&1; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/s1_ladder.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
