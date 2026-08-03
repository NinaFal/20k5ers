#!/usr/bin/env bash
# Supervisor for the 2016-2025 gauntlet. Usage: w5_gauntlet_supervisor.sh <stage> [top]
#
# The gauntlet is up to 20 configs x 10 years of full-year backtests, which is
# far longer than this container's restart cadence. w5_gauntlet.py writes its
# results json after every single (config, year), so a kill costs at most one
# year and the relaunch picks up exactly where it stopped.
cd /home/user/20k5ers || exit 1
STAGE=${1:?stage required}
TOP=${2:-20}
LOG="backtest/output/doe/wall5/${STAGE}_gauntlet_run.log"
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
for ((i = 0; i < 500; i++)); do
  while pgrep -f "w5_gauntlet.py --stage ${STAGE}" >/dev/null 2>&1; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] ${STAGE} gauntlet complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_gauntlet.py --stage "$STAGE" \
    --top "$TOP" >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
