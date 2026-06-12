#!/usr/bin/env bash
# watchdog_stage3.sh — supervised launcher for Stage 3 TP-ladder Optuna run.
#
# Same pattern as watchdog_stage2.sh: setsid nohup detached daemon, 5-min
# commit/push cycle, restart-safe (reads DB for real trial count).
#
# Launch:
#   STAGE3_TRIALS=100 STAGE3_JOBS=4 \
#     setsid nohup bash backtest/src/watchdog_stage3.sh \
#     >> backtest/output/doe/watchdog_stage3.log 2>&1 &
#
# Env vars:
#   STAGE3_TRIALS (default 100)
#   STAGE3_JOBS   (default 1)

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

TRIALS="${STAGE3_TRIALS:-100}"
JOBS="${STAGE3_JOBS:-4}"

LOG="backtest/output/doe/stage3_run.log"
CSV="backtest/output/doe/stage3.csv"
DB="backtest/output/doe/stage3.db"

LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 \
  python -u backtest/src/stage3_tp_ladder.py --trials $TRIALS --jobs $JOBS \
  >> $LOG 2>&1"

ts()         { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
    git add -f "$LOG" "$CSV" "$DB" watchdog_stage3.log 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "chore: stage3 checkpoint $(ts)

https://claude.ai/code/session_01918TqV5qt4q9btnBdakxXJ" --quiet 2>/dev/null || true
        git push -u origin "$(git rev-parse --abbrev-ref HEAD)" --quiet 2>/dev/null || true
    fi
}

count_csv() {
    local f="$1"
    local n; n=$([ -f "$f" ] && awk 'NR>1{c++}END{print c+0}' "$f" 2>/dev/null); echo "${n:-0}"
}

done_marker() {
    local f="$1"; [ -f "$f" ] || { echo 0; return; }
    local n; n=$(grep -c "STAGE3_DONE_MARKER" "$f" 2>/dev/null); echo "${n:-0}"
}

echo "[$(ts)] watchdog_stage3 starting (TRIALS=$TRIALS JOBS=$JOBS pid=$$)"

while true; do
    DONE=$(done_marker "$LOG")
    DC=$(count_csv "$CSV")

    if [ "${DONE:-0}" -ge 1 ]; then
        commit_push
        echo "[$(ts)] STAGE3_ALL_COMPLETE — $DC CSV rows, watchdog exiting"
        break
    fi

    if pgrep -f "stage3_tp_ladder.py" > /dev/null 2>&1; then
        echo "[$(ts)] ALIVE (csv=$DC/$TRIALS)"
    else
        echo "[$(ts)] DEAD (csv=$DC/$TRIALS) — relaunching"
        commit_push
        eval "$LAUNCH &"
        sleep 8
        if pgrep -f "stage3_tp_ladder.py" > /dev/null 2>&1; then
            echo "[$(ts)] RELAUNCHED ok"
        else
            echo "[$(ts)] RELAUNCH FAILED — check $LOG"
        fi
    fi

    commit_push
    sleep 300
done
