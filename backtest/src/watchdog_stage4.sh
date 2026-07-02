#!/usr/bin/env bash
# watchdog_stage4.sh — supervised launcher for Stage 4 validation gauntlet.
#
# Launch:
#   setsid nohup bash backtest/src/watchdog_stage4.sh \
#     >> backtest/output/doe/watchdog_stage4.log 2>&1 &
#
# Env vars:
#   STAGE4_SUITE   suite to run (default: all)
#   VAL_WORKERS    parallel workers (default: 2)

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

SUITE="${STAGE4_SUITE:-all}"
WORKERS="${VAL_WORKERS:-2}"

LOG="backtest/output/doe/stage4_run.log"
JSON="backtest/output/doe/stage4_validation.json"
RPT="backtest/output/doe/stage4_validation_report.txt"

LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=9999 \
  VAL_WORKERS=$WORKERS \
  python -u backtest/src/stage4_validate.py --suite $SUITE \
  >> $LOG 2>&1"

ts()          { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
    git add -f "$LOG" "$JSON" "$RPT" watchdog_stage4.log 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "chore: stage4 checkpoint $(ts)" --quiet 2>/dev/null || true
        git push -u origin "$(git rev-parse --abbrev-ref HEAD)" --quiet 2>/dev/null || true
    fi
}

count_done() {
    [ -f "$JSON" ] || { echo 0; return; }
    python3 -c "
import json, sys
d = json.load(open('$JSON'))
print(len(d.get('oos',[])) + len(d.get('train',[])) + len(d.get('gap',[])) + len(d.get('walk',[])))
" 2>/dev/null || echo 0
}

done_marker() {
    local f="$1"; [ -f "$f" ] || { echo 0; return; }
    local n; n=$(grep -c "STAGE4_VALIDATION_DONE_MARKER" "$f" 2>/dev/null); echo "${n:-0}"
}

echo "[$(ts)] watchdog_stage4 starting (SUITE=$SUITE WORKERS=$WORKERS pid=$$)"

while true; do
    DONE=$(done_marker "$LOG")
    DC=$(count_done)

    if [ "${DONE:-0}" -ge 1 ]; then
        commit_push
        echo "[$(ts)] STAGE4_ALL_COMPLETE — $DC runs done, watchdog exiting"
        break
    fi

    if pgrep -f "stage4_validate.py" > /dev/null 2>&1; then
        echo "[$(ts)] ALIVE (done=$DC runs)"
    else
        echo "[$(ts)] DEAD (done=$DC) — relaunching"
        commit_push
        eval "$LAUNCH &"
        sleep 10
        if pgrep -f "stage4_validate.py" > /dev/null 2>&1; then
            echo "[$(ts)] RELAUNCHED ok"
        else
            echo "[$(ts)] RELAUNCH FAILED — check $LOG"
        fi
    fi

    commit_push
    sleep 300
done
