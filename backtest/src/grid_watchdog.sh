#!/usr/bin/env bash
# Detached overnight watchdog for the Stage 1c grid.
# Runs independently of Claude Monitor (which caps at ~30 min). Survives until
# the container is reclaimed. Every 20 min: ensure grid alive (relaunch if not),
# commit + push the CSV checkpoint, stop at 692 cells.
#
# Launch detached:
#   setsid nohup bash backtest/src/grid_watchdog.sh >> backtest/output/doe/grid_watchdog.log 2>&1 &
#
# Stop:
#   pkill -f grid_watchdog.sh

set -u
cd /home/user/20k5ers || exit 1

CSV="backtest/output/doe/stage1c_grid.csv"
BRANCH="claude/awesome-maxwell-50dMF"
LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 DOE_WORKERS_SHORT=4 RUN_TIMEOUT_S=2400 python -u backtest/src/stage1_entry_quality.py --phase grid >> backtest/output/doe/stage1c_grid_run.log 2>&1"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
  git add "$CSV" >/dev/null 2>&1
  if ! git diff --cached --quiet >/dev/null 2>&1; then
    git commit -m "Stage 1c checkpoint $1/692 cells" >/dev/null 2>&1
    for i in 1 2 4 8; do
      git push -u origin "$BRANCH" >/dev/null 2>&1 && break
      sleep "$i"
    done
  fi
}

echo "[$(ts)] watchdog started (pid $$)"

while true; do
  DONE=0
  [ -f "$CSV" ] && DONE=$(( $(wc -l < "$CSV") - 1 ))

  BEST=$(awk -F',' 'NR>1 && $11=="False"{if($28+0>b+0)b=$28} END{printf "%.1f", b+0}' "$CSV" 2>/dev/null || echo "?")

  if [ "$DONE" -ge 692 ]; then
    commit_push "$DONE"
    echo "[$(ts)] GRID_COMPLETE done=692/692 best=$BEST — launching Stage 1d"
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
      PYTHONUTF8=1 DOE_WORKERS_SHORT=4 RUN_TIMEOUT_S=2400 \
      python -u backtest/src/stage1d_lower_calm_fibs.py \
      >> backtest/output/doe/stage1d_run.log 2>&1
    git add "$CSV" backtest/output/doe/stage1d_run.log >/dev/null 2>&1
    git diff --cached --quiet >/dev/null 2>&1 || git commit -m "Stage 1d complete — 1c+1d unified results" >/dev/null 2>&1
    for i in 1 2 4 8; do git push -u origin "$BRANCH" >/dev/null 2>&1 && break; sleep "$i"; done
    echo "[$(ts)] STAGE1D_COMPLETE — all entry-quality cells done, watchdog exiting"
    break
  fi

  if pgrep -f stage1_entry_quality.py > /dev/null 2>&1; then
    echo "[$(ts)] ALIVE done=$DONE/692 best=$BEST"
  else
    echo "[$(ts)] DEAD — relaunching (done=$DONE/692 best=$BEST)"
    commit_push "$DONE"
    eval "$LAUNCH &"
    sleep 5
    if pgrep -f stage1_entry_quality.py > /dev/null 2>&1; then
      echo "[$(ts)] RELAUNCHED ok"
    else
      echo "[$(ts)] RELAUNCH_FAILED — check stage1c_grid_run.log"
    fi
  fi

  commit_push "$DONE"
  sleep 1200   # 20 minutes
done
