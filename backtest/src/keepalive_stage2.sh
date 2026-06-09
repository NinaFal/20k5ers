#!/usr/bin/env bash
# Keepalive for Stage 2 (sizing/risk Optuna). Runs entry A to its trial target,
# then entry B. Optuna sqlite (stage2_A.db / stage2_B.db) makes each resumable,
# so a relaunch just continues. Commits+pushes the DBs every cycle. Exits once
# BOTH entries print STAGE2_DONE_MARKER in the log.
#
# CRITICAL: Never use & to background the optimizer — in the Firecracker container
# PID 1 reaps any orphan immediately. Run the optimizer in the FOREGROUND and let
# this keepalive wait for it. This script itself is launched via run_in_background:true
# on the Bash tool so the harness process (not bash &) is the parent.
cd /home/user/20k5ers || exit 1
BRANCH="claude/awesome-maxwell-50dMF"
TRIALS="${STAGE2_TRIALS:-100}"
JOBS="${STAGE2_JOBS:-1}"
LOG="backtest/output/doe/stage2_run.log"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_push() {
  git add backtest/output/doe/stage2_A.db backtest/output/doe/stage2_B.db >/dev/null 2>&1
  if ! git diff --cached --quiet >/dev/null 2>&1; then
    git commit -m "Stage 2 checkpoint (Optuna study)" >/dev/null 2>&1
    for i in 1 2 4 8; do git push -u origin "$BRANCH" >/dev/null 2>&1 && break; sleep "$i"; done
  fi
}

done_marker() {
  [ -f "$LOG" ] || { echo 0; return; }
  local n; n=$(grep -c "stage2 $1] STAGE2_DONE_MARKER" "$LOG" 2>/dev/null)
  echo "${n:-0}"
}

run_entry() {
  local entry="$1"
  echo "[$(ts)] launching stage2 $entry (target $TRIALS trials, jobs=$JOBS)" | tee -a "$LOG"
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  NUMEXPR_NUM_THREADS=1 PYTHONUTF8=1 RUN_TIMEOUT_S=2400 \
  python -u backtest/src/stage2_sizing_risk.py \
    --entry "$entry" --trials "$TRIALS" --jobs "$JOBS" >> "$LOG" 2>&1
  echo "[$(ts)] stage2 $entry process exited" | tee -a "$LOG"
  commit_push
}

echo "[$(ts)] keepalive_stage2 starting (TRIALS=$TRIALS JOBS=$JOBS)" | tee -a "$LOG"

while true; do
  A_DONE=$(done_marker A); B_DONE=$(done_marker B)

  if [ "${A_DONE:-0}" -ge 1 ] && [ "${B_DONE:-0}" -ge 1 ]; then
    commit_push
    echo "[$(ts)] STAGE2_ALL_COMPLETE — both entries done, keepalive exiting" | tee -a "$LOG"
    break
  fi

  # Hard concurrency guard: never allow two stage2 processes at once
  if pgrep -f "stage2_sizing_risk.py" > /dev/null 2>&1; then
    echo "[$(ts)] stage2 optimizer already running — waiting 60s" | tee -a "$LOG"
    sleep 60
    continue
  fi

  # Pick entry: A first, then B
  if [ "${A_DONE:-0}" -lt 1 ]; then
    run_entry A
  else
    run_entry B
  fi

  commit_push
  sleep 10
done
