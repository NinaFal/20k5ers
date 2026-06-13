#!/usr/bin/env bash
# watchdog_stage4_pareto.sh — supervised launcher for Stage 4 Pareto optimizer.
#
# Launch:
#   setsid nohup bash backtest/src/watchdog_stage4_pareto.sh \
#     >> backtest/output/doe/watchdog_stage4_pareto.log 2>&1 &
#
# Env vars:
#   PARETO_TRIALS   total Optuna trials (default 200)
#   VAL_WORKERS     parallel workers   (default 2)

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TRIALS="${PARETO_TRIALS:-200}"
WORKERS="${VAL_WORKERS:-2}"

LOG="backtest/output/doe/stage4_pareto_run.log"
RPT="backtest/output/doe/stage4_pareto_report.txt"
CSV="backtest/output/doe/stage4_pareto.csv"

LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=9999 \
  VAL_WORKERS=$WORKERS \
  python -u backtest/src/stage4_pareto.py --trials $TRIALS \
  >> $LOG 2>&1"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
    git add -f "$LOG" "$RPT" "$CSV" watchdog_stage4_pareto.log 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "chore: stage4 pareto checkpoint $(ts)" --quiet 2>/dev/null || true
        git push -u origin "$(git rev-parse --abbrev-ref HEAD)" --quiet 2>/dev/null || true
    fi
}

done_marker() {
    local f="$1"; [ -f "$f" ] || { echo 0; return; }
    grep -c "STAGE4_PARETO_DONE_MARKER" "$f" 2>/dev/null || echo 0
}

is_running() {
    ps -eo comm,args --no-headers 2>/dev/null \
      | awk '$1 ~ /^python/ && /stage4_pareto\.py/ {found=1} END{exit found?0:1}'
}

echo "[$(ts)] watchdog_stage4_pareto starting (TRIALS=$TRIALS WORKERS=$WORKERS pid=$$)"

while true; do
    if [ "$(done_marker "$LOG")" -ge 1 ]; then
        commit_push
        echo "[$(ts)] STAGE4_PARETO_ALL_COMPLETE — watchdog exiting"
        break
    fi

    if is_running; then
        echo "[$(ts)] ALIVE"
    else
        echo "[$(ts)] DEAD — relaunching"
        commit_push
        eval "$LAUNCH &"
        sleep 10
        if is_running; then
            echo "[$(ts)] RELAUNCHED ok"
        else
            echo "[$(ts)] RELAUNCH FAILED — check $LOG"
        fi
    fi

    commit_push
    sleep 300
done
