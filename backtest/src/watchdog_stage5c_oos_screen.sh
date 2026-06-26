#!/usr/bin/env bash
# watchdog_stage5c_oos_screen.sh — supervises Stage 5c OOS screener.
#
# Launch:
#   SCREEN_TOP=20 VAL_WORKERS=4 setsid nohup bash backtest/src/watchdog_stage5c_oos_screen.sh \
#     >> backtest/output/doe/watchdog_stage5c_oos_screen.log 2>&1 &

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TOP="${SCREEN_TOP:-20}"
WORKERS="${VAL_WORKERS:-4}"
LOG="backtest/output/doe/stage5c_oos_screen_run.log"
JSON="backtest/output/doe/stage5c_oos_screen.json"
REPORT="backtest/output/doe/stage5c_oos_screen_report.txt"

LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=999999 \
  VAL_WORKERS=$WORKERS \
  python -u backtest/src/stage5c_oos_screen.py --top $TOP --workers $WORKERS \
  >> $LOG 2>&1"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
    git add -f "$LOG" "$JSON" "$REPORT" watchdog_stage5c_oos_screen.log 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "chore: stage5c oos screen checkpoint $(ts)" --quiet 2>/dev/null || true
        git push -u origin "$(git rev-parse --abbrev-ref HEAD)" --quiet 2>/dev/null || true
    fi
}

done_marker() {
    [ -f "$LOG" ] || { echo 0; return; }
    grep -c "STAGE5C_OOS_SCREEN_DONE_MARKER" "$LOG" 2>/dev/null || echo 0
}

is_running() {
    ps -eo comm,args --no-headers 2>/dev/null \
      | awk '$1 ~ /^python/ && /stage5c_oos_screen\.py/ {found=1} END{exit found?0:1}'
}

echo "[$(ts)] watchdog_stage5c_oos_screen starting (TOP=$TOP WORKERS=$WORKERS pid=$$)"

while true; do
    if [ "$(done_marker)" -ge 1 ]; then
        commit_push
        echo "[$(ts)] STAGE5C_OOS_SCREEN_DONE — watchdog exiting"
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
