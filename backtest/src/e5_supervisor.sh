#!/usr/bin/env bash
# Supervisor for the E5 gauntlet. The container restarts periodically and kills
# everything; E5 caches per start window, so a restart costs at most one window.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/e5_run.log
CHECKS="${*:-holdout tenyear random robust}"
for ((i = 0; i < 200; i++)); do
  while pgrep -f "e5_validate_winner.py" >/dev/null 2>&1; do sleep 30; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] gauntlet complete" >>"$LOG"; exit 0
  fi
  echo "[SUP] restart #$((i + 1)) — checks: $CHECKS" >>"$LOG"
  setsid nohup uv run python3 backtest/src/e5_validate_winner.py \
    --checks $CHECKS >>"$LOG" 2>&1 </dev/null &
  sleep 20
done
