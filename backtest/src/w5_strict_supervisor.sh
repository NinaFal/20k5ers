#!/usr/bin/env bash
# Supervisor for a STRICT-marking stage (TDD_WORST_CASE forced on via W5_STRICT).
# Usage: w5_strict_supervisor.sh <stage> [trials] [screen] [workers]
cd /home/user/20k5ers || exit 1
STAGE=${1:?stage required}; TRIALS=${2:-120}; SCREEN=${3:-25}; WORKERS=${4:-3}
LOG="backtest/output/doe/wall5/${STAGE}_run.log"
mkdir -p backtest/output/doe/wall5 backtest/output/doe/tmp
touch "$LOG"
running() { ps -eo cmd --no-headers | grep -q "^python3 backtest/src/w5_stage.py --stage ${STAGE} "; }
for ((i = 0; i < 500; i++)); do
  while running; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] ${STAGE} complete" >>"$LOG"; exit 0
  fi
  W5_STRICT=1 W5_WORKERS="$WORKERS" setsid nohup uv run python3 backtest/src/w5_stage.py \
    --stage "$STAGE" --trials "$TRIALS" --screen "$SCREEN" --round 1 >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
