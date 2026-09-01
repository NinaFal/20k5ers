#!/usr/bin/env bash
# Supervisor for the continuous 2016-2025 run.
#
# Liveness is ANCHORED to the real command line. A bare `pgrep -f w5_continuous`
# also matches the shell that launched this script, which would leave the
# supervisor waiting on a process that is not the job.
#
# Unlike the per-year gauntlet this caches nothing mid-run, so a container
# restart costs the whole attempt and the retry starts from 2016 again.
cd /home/user/20k5ers || exit 1
LOG=backtest/output/doe/wall5/continuous_run.log
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
running() {
  ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_continuous"
}
for ((i = 0; i < 500; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] continuous complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_continuous.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
