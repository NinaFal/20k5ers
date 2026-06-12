#!/usr/bin/env bash
# watchdog_stage4_robustness.sh — supervised launcher for the Stage 4
# robustness gauntlet (worst-case intrabar TDD, Monte-Carlo shuffle,
# parameter perturbation).
#
# Launch:
#   setsid nohup bash backtest/src/watchdog_stage4_robustness.sh \
#     >> backtest/output/doe/watchdog_stage4_robustness.log 2>&1 &
#
# Env vars:
#   MC_ITER  Monte-Carlo iterations (default 5000)

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

MC="${MC_ITER:-5000}"

LOG="backtest/output/doe/stage4_robustness_run.log"
JSON="backtest/output/doe/stage4_robustness.json"
RPT="backtest/output/doe/stage4_robustness_report.txt"

LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=9999 \
  python -u backtest/src/stage4_robustness.py --suite all --mc $MC \
  >> $LOG 2>&1"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
    git add -f "$JSON" "$RPT" watchdog_stage4_robustness.log 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "chore: stage4 robustness checkpoint $(ts)" --quiet 2>/dev/null || true
        git push -u origin "$(git rev-parse --abbrev-ref HEAD)" --quiet 2>/dev/null || true
    fi
}

done_marker() {
    local f="$1"; [ -f "$f" ] || { echo 0; return; }
    local n; n=$(grep -c "STAGE4_ROBUSTNESS_DONE_MARKER" "$f" 2>/dev/null); echo "${n:-0}"
}

# Detect the REAL python process only — match on comm=python* so transient
# bash/diagnostic command lines that merely mention the script name (snapshot
# wrappers, ad-hoc pgrep checks) never count as a false "ALIVE".
is_running() {
    ps -eo comm,args --no-headers 2>/dev/null \
      | awk '$1 ~ /^python/ && /stage4_robustness\.py/ {found=1} END{exit found?0:1}'
}

echo "[$(ts)] watchdog_stage4_robustness starting (MC=$MC pid=$$)"

while true; do
    DONE=$(done_marker "$LOG")
    if [ "${DONE:-0}" -ge 1 ]; then
        commit_push
        echo "[$(ts)] STAGE4_ROBUSTNESS_ALL_COMPLETE — watchdog exiting"
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
