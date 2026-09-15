#!/usr/bin/env bash
# Restart-tolerant supervisor for the backup-vs-incumbent comparison.
#
# The liveness check is ANCHORED to the real command line ("^uv run python3 ...").
# A bare `pgrep -f w5_backup_compare.py` also matches the shell that launched
# this script — that shell's command line contains the script name — so the
# supervisor waits on a process that is not the job and never starts anything.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/backup_compare_run.log
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
running() {
  ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_backup_compare"
}
for ((i = 0; i < 500; i++)); do
  while running; do sleep 20; done
  grep -q "DONE_MARKER" "$LOG" 2>/dev/null && { echo "[SUP] cmp complete" >>"$LOG"; exit 0; }
  setsid nohup uv run python3 backtest/src/w5_backup_compare.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
