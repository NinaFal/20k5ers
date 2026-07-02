#!/usr/bin/env bash
# Keepalive for Stage 1d (c=0.35/0.40, 18 cells). Same pattern as keepalive.sh.
# Relaunches stage1d_lower_calm_fibs.py if it dies; commits+pushes CSV every cycle;
# exits once all 18 Stage 1d cells are present in the CSV.
cd /home/user/20k5ers || exit 1
CSV="backtest/output/doe/stage1c_grid.csv"
BRANCH="claude/awesome-maxwell-50dMF"
LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 DOE_WORKERS_SHORT=4 RUN_TIMEOUT_S=2400 python -u backtest/src/stage1d_lower_calm_fibs.py >> backtest/output/doe/stage1d_run.log 2>&1"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
  git add "$CSV" backtest/output/doe/stage1d_run.log >/dev/null 2>&1
  if ! git diff --cached --quiet >/dev/null 2>&1; then
    git commit -m "Stage 1d checkpoint" >/dev/null 2>&1
    for i in 1 2 4 8; do git push -u origin "$BRANCH" >/dev/null 2>&1 && break; sleep "$i"; done
  fi
}

while true; do
  # Count Stage 1d cells done: calm fib 0.35 or 0.40 rows in the CSV
  D1D=$(awk -F',' 'NR>1 && ($1=="0.35"||$1=="0.4"||$1=="0.40"){n++} END{print n+0}' "$CSV" 2>/dev/null)
  if [ "${D1D:-0}" -ge 18 ]; then
    commit_push
    echo "[$(ts)] STAGE1D_COMPLETE — $D1D/18 cells, keepalive exiting"
    break
  fi
  if ! pgrep -f stage1d_lower_calm_fibs.py > /dev/null 2>&1; then
    echo "[$(ts)] 1d dead (done=$D1D/18) — relaunching"
    commit_push
    eval "$LAUNCH &"
    sleep 5
  else
    echo "[$(ts)] 1d ALIVE done=$D1D/18"
  fi
  commit_push
  sleep 300
done
