#!/usr/bin/env bash
# Restart-tolerant supervisor for the backup-vs-incumbent comparison.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/backup_compare_run.log
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
for ((i = 0; i < 500; i++)); do
  while pgrep -f "w5_backup_compare.py" >/dev/null 2>&1; do sleep 20; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] cmp complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_backup_compare.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
