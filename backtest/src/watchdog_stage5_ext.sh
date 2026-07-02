#!/usr/bin/env bash
# watchdog_stage5_ext.sh — extended Stage 5 optimizer run (300 more trials → 450 total).
#
# Resumes the same Optuna SQLite study (stage5.db) from where it left off.
# Uses a fresh log so the original stage5_run.log / DONE_MARKER is not clobbered.
#
# Launch:
#   STAGE5_TRIALS=450 setsid nohup bash backtest/src/watchdog_stage5_ext.sh \
#     >> backtest/output/doe/watchdog_stage5_ext.log 2>&1 &

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TRIALS="${STAGE5_TRIALS:-450}"
WORKERS="${VAL_WORKERS:-4}"
LOG="backtest/output/doe/stage5_ext_run.log"
CSV="backtest/output/doe/stage5.csv"

LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=999999 \
  VAL_WORKERS=$WORKERS \
  python -u backtest/src/stage5_risk_regime.py --trials $TRIALS --jobs $WORKERS \
  >> $LOG 2>&1"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
    git add -f "$LOG" "$CSV" watchdog_stage5_ext.log 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "chore: stage5 ext optimizer checkpoint $(ts)" --quiet 2>/dev/null || true
        git push -u origin "$(git rev-parse --abbrev-ref HEAD)" --quiet 2>/dev/null || true
    fi
}

done_marker() {
    local f="$1" n
    [ -f "$f" ] || { echo 0; return; }
    n=$(grep -c "STAGE5_DONE_MARKER" "$f" 2>/dev/null) || n=0
    echo "$n"
}

is_running() {
    ps -eo comm,args --no-headers 2>/dev/null \
      | awk '$1 ~ /^python/ && /stage5_risk_regime\.py/ {found=1} END{exit found?0:1}'
}

echo "[$(ts)] watchdog_stage5_ext starting (TRIALS=$TRIALS WORKERS=$WORKERS pid=$$)"

while true; do
    if [ "$(done_marker "$LOG")" -ge 1 ]; then
        commit_push
        echo "[$(ts)] STAGE5_EXT_ALL_COMPLETE — watchdog exiting"
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
