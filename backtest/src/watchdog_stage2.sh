#!/usr/bin/env bash
# Stage 2 sizing/risk watchdog. Mirrors grid_watchdog.sh exactly:
#   - setsid nohup launched (survives Claude session restarts)
#   - eval "$LAUNCH &" worker (child of watchdog, not orphan)
#   - commit+push CSV+DB every 5 min
#   - sequential: entry A to completion, then entry B
#   - exits when both entries print STAGE2_DONE_MARKER
#
# Launch (detached):
#   cd /home/user/20k5ers
#   setsid nohup bash backtest/src/watchdog_stage2.sh >> backtest/output/doe/watchdog_stage2.log 2>&1 &
#
# Stop:
#   pkill -f watchdog_stage2.sh
#
# Env overrides:
#   STAGE2_TRIALS (default 100)   STAGE2_JOBS (default 1)

set -u
cd /home/user/20k5ers || exit 1

BRANCH="claude/awesome-maxwell-50dMF"
TRIALS="${STAGE2_TRIALS:-100}"
JOBS="${STAGE2_JOBS:-1}"
LOG_A="backtest/output/doe/stage2_A_run.log"
LOG_B="backtest/output/doe/stage2_B_run.log"
CSV_A="backtest/output/doe/stage2_A.csv"
CSV_B="backtest/output/doe/stage2_B.csv"
DB_A="backtest/output/doe/stage2_A.db"
DB_B="backtest/output/doe/stage2_B.db"

LAUNCH_A="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=7200 python -u backtest/src/stage2_sizing_risk.py --entry A --trials $TRIALS --jobs $JOBS >> $LOG_A 2>&1"
LAUNCH_B="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=7200 python -u backtest/src/stage2_sizing_risk.py --entry B --trials $TRIALS --jobs $JOBS >> $LOG_B 2>&1"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

count_csv() {
  local f="$1"; [ -f "$f" ] && awk 'NR>1{c++}END{print c+0}' "$f" || echo 0
}

done_marker() {
  local f="$1"; [ -f "$f" ] || { echo 0; return; }
  grep -c "STAGE2_DONE_MARKER" "$f" 2>/dev/null || echo 0
}

commit_push() {
  local da; da=$(count_csv "$CSV_A")
  local db; db=$(count_csv "$CSV_B")
  git add "$CSV_A" "$CSV_B" "$DB_A" "$DB_B" "$LOG_A" "$LOG_B" >/dev/null 2>&1
  if ! git diff --cached --quiet >/dev/null 2>&1; then
    git commit -m "Stage 2 checkpoint A=${da} B=${db} trials" >/dev/null 2>&1
    for i in 1 2 4 8; do
      git push -u origin "$BRANCH" >/dev/null 2>&1 && break
      sleep "$i"
    done
  fi
}

echo "[$(ts)] watchdog_stage2 starting (TRIALS=$TRIALS JOBS=$JOBS pid=$$)"

while true; do
  A_DONE=$(done_marker "$LOG_A")
  B_DONE=$(done_marker "$LOG_B")
  DA=$(count_csv "$CSV_A")
  DB=$(count_csv "$CSV_B")

  if [ "${A_DONE:-0}" -ge 1 ] && [ "${B_DONE:-0}" -ge 1 ]; then
    commit_push
    echo "[$(ts)] STAGE2_ALL_COMPLETE — A=${DA} B=${DB} trials, watchdog exiting"
    break
  fi

  # Entry A first, then B
  if [ "${A_DONE:-0}" -lt 1 ]; then
    if pgrep -f "stage2_sizing_risk.py.*--entry A" > /dev/null 2>&1; then
      echo "[$(ts)] A ALIVE (done=$DA/$TRIALS)"
    else
      echo "[$(ts)] A DEAD (done=$DA/$TRIALS) — relaunching"
      commit_push
      eval "$LAUNCH_A &"
      sleep 5
      if pgrep -f "stage2_sizing_risk.py.*--entry A" > /dev/null 2>&1; then
        echo "[$(ts)] A RELAUNCHED ok"
      else
        echo "[$(ts)] A RELAUNCH FAILED — check $LOG_A"
      fi
    fi
  else
    if pgrep -f "stage2_sizing_risk.py.*--entry B" > /dev/null 2>&1; then
      echo "[$(ts)] B ALIVE (done=$DB/$TRIALS)"
    else
      echo "[$(ts)] B DEAD (done=$DB/$TRIALS) — relaunching"
      commit_push
      eval "$LAUNCH_B &"
      sleep 5
      if pgrep -f "stage2_sizing_risk.py.*--entry B" > /dev/null 2>&1; then
        echo "[$(ts)] B RELAUNCHED ok"
      else
        echo "[$(ts)] B RELAUNCH FAILED — check $LOG_B"
      fi
    fi
  fi

  commit_push
  sleep 300  # 5 minutes
done
