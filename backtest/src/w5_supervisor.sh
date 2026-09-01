#!/usr/bin/env bash
# Supervisor for the 5%-wall round. Usage: w5_supervisor.sh <stage> [trials] [screen]
# The container restarts every few minutes and has rebuilt itself from scratch
# once; the Optuna study and the per-(config,start) cache both resume, so a kill
# costs at most one start.
cd /home/user/20k5ers || exit 1
STAGE=${1:?stage required}
TRIALS=${2:-120}
SCREEN=${3:-25}
ROUND=${4:-1}
TAG=$([ "${ROUND:-1}" = "1" ] && echo "$STAGE" || echo "${STAGE}_r${ROUND}")
LOG="backtest/output/doe/wall5/${TAG}_run.log"
mkdir -p backtest/output/doe/wall5
touch "$LOG"
for ((i = 0; i < 500; i++)); do
  while pgrep -f "w5_stage.py --stage ${STAGE} --trials ${TRIALS} --screen ${SCREEN} --round ${ROUND}" >/dev/null 2>&1; do sleep 20; done
  if grep -q "DONE_MARKER" "$LOG" 2>/dev/null; then
    echo "[SUP] ${STAGE} complete" >>"$LOG"; exit 0
  fi
  setsid nohup uv run python3 backtest/src/w5_stage.py --stage "$STAGE" \
    --trials "$TRIALS" --screen "$SCREEN" --round "${ROUND:-1}" >>"$LOG" 2>&1 </dev/null &
  sleep 15
done
