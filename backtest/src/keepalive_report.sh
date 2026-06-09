#!/usr/bin/env bash
# Keepalive for the Stage 1c/1d entry-quality MFE report.
# The report has per-finalist checkpointing (skip-if-done in
# stage1c_entry_quality_report.csv), so relaunching simply resumes.
# Exits once the report process finishes cleanly (all finalists checkpointed).
cd /home/user/20k5ers || exit 1
BRANCH="claude/awesome-maxwell-50dMF"
TOP="${REPORT_TOP:-16}"
LOG="backtest/output/doe/stage1c_report_run.log"
RCSV="backtest/output/doe/stage1c_entry_quality_report.csv"
LAUNCH="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 DOE_WORKERS_SHORT=4 RUN_TIMEOUT_S=2400 python -u backtest/src/stage1c_entry_quality_report.py --top $TOP >> $LOG 2>&1"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
  git add "$RCSV" >/dev/null 2>&1
  if ! git diff --cached --quiet >/dev/null 2>&1; then
    git commit -m "Entry-quality report checkpoint" >/dev/null 2>&1
    for i in 1 2 4 8; do git push -u origin "$BRANCH" >/dev/null 2>&1 && break; sleep "$i"; done
  fi
}

while true; do
  # Done when the report log shows the final ranked table footer.
  if grep -q "ENTRY-QUALITY REPORT COMPLETE" "$LOG" 2>/dev/null; then
    commit_push
    echo "[$(ts)] REPORT_COMPLETE — keepalive exiting"
    break
  fi
  if ! pgrep -f stage1c_entry_quality_report.py > /dev/null 2>&1; then
    DONE=0; [ -f "$RCSV" ] && DONE=$(( $(wc -l < "$RCSV") - 1 ))
    echo "[$(ts)] report dead (done=$DONE finalists) — relaunching"
    commit_push
    eval "$LAUNCH &"
    sleep 5
  else
    DONE=0; [ -f "$RCSV" ] && DONE=$(( $(wc -l < "$RCSV") - 1 ))
    echo "[$(ts)] report ALIVE (done=$DONE finalists)"
  fi
  commit_push
  sleep 180
done
