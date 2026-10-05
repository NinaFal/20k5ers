#!/usr/bin/env bash
# Waits for the continuous scaling decade to finish before starting the scaling
# drawdown probe. The box has 4 cores and the 100-start holdout already owns all
# four; the holdout is the priority job, so the probe slots into the core the
# continuous run gives back rather than competing for one now.
cd /home/user/20k5ers || exit 1
CCLOG=backtest/output/doe/wall5/continuous_chunked_run.log
LOG=backtest/output/doe/wall5/scaling_probe_run.log
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^uv run python3 backtest/src/w5_scaling_dd_probe"; }
for ((i = 0; i < 240; i++)); do
  grep -q "w5_continuous_chunked. DONE_MARKER" "$CCLOG" 2>/dev/null && break
  sleep 60
done
for ((i = 0; i < 300; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] probe complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_scaling_dd_probe.py >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
