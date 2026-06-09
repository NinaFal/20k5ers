#!/usr/bin/env bash
# Keepalive for Stage 2 (sizing/risk Optuna). Runs entry A to its trial target,
# then entry B. Optuna sqlite (stage2_A.db / stage2_B.db) makes each resumable,
# so a relaunch just continues. Commits+pushes the DBs every cycle. Exits once
# BOTH entries print STAGE2_DONE_MARKER in the log.
cd /home/user/20k5ers || exit 1
BRANCH="claude/awesome-maxwell-50dMF"
TRIALS="${STAGE2_TRIALS:-100}"
JOBS="${STAGE2_JOBS:-2}"
LOG="backtest/output/doe/stage2_run.log"
ENVP="OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=2400"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
  git add backtest/output/doe/stage2_A.db backtest/output/doe/stage2_B.db >/dev/null 2>&1
  if ! git diff --cached --quiet >/dev/null 2>&1; then
    git commit -m "Stage 2 checkpoint (Optuna study)" >/dev/null 2>&1
    for i in 1 2 4 8; do git push -u origin "$BRANCH" >/dev/null 2>&1 && break; sleep "$i"; done
  fi
}

done_marker() {
  # Emit a single integer count. grep -c prints "0" and exits 1 on no-match, so we
  # must capture (not `|| echo 0`, which would double-print) and default if empty.
  [ -f "$LOG" ] || { echo 0; return; }
  local n; n=$(grep -c "stage2 $1] STAGE2_DONE_MARKER" "$LOG" 2>/dev/null)
  echo "${n:-0}"
}

while true; do
  A_DONE=$(done_marker A); B_DONE=$(done_marker B)
  if [ "${A_DONE:-0}" -ge 1 ] && [ "${B_DONE:-0}" -ge 1 ]; then
    commit_push
    echo "[$(ts)] STAGE2_ALL_COMPLETE — both entries done, keepalive exiting"
    break
  fi

  # Pick which entry to run: A first, then B.
  if [ "${A_DONE:-0}" -lt 1 ]; then ENTRY=A; else ENTRY=B; fi

  # Hard guard: never allow two entries concurrently (memory pressure corrupts
  # results). If ANY stage2 optimizer is running, assume it's the right one.
  if pgrep -f "stage2_sizing_risk.py" > /dev/null 2>&1; then
    echo "[$(ts)] stage2 optimizer ALIVE (target entry $ENTRY)"
  else
    echo "[$(ts)] stage2 $ENTRY not running — launching (target $TRIALS trials)"
    commit_push
    eval "$ENVP python -u backtest/src/stage2_sizing_risk.py --entry $ENTRY --trials $TRIALS --jobs $JOBS >> $LOG 2>&1 &"
    sleep 5
  fi
  commit_push
  sleep 300
done
