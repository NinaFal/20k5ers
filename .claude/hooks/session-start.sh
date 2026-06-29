#!/bin/bash
# SessionStart hook: pull latest state and relaunch the active watchdog on every
# container boot. Combined with the watchdog (relaunches Python if it dies) and
# per-window checkpointing (no work lost mid-trial), this makes the backend
# survive any process death OR full container restart with no manual action.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd /home/user/20k5ers
git pull origin claude/awesome-maxwell-50dMF --quiet 2>/dev/null || true
mkdir -p backtest/output/doe

# ── Active job: Stage 5c OOS screen ──────────────────────────────────────────
SCREEN_LOG="backtest/output/doe/stage5c_oos_screen_run.log"
if grep -q "STAGE5C_OOS_SCREEN_DONE_MARKER" "$SCREEN_LOG" 2>/dev/null; then
  echo "[session-start] Stage 5c OOS screen COMPLETE — nothing to relaunch"
  exit 0
fi

if pgrep -f "watchdog_stage5c_oos_screen.sh" > /dev/null 2>&1; then
  echo "[session-start] Stage 5c OOS screen watchdog already running"
  exit 0
fi

SCREEN_TOP=20 VAL_WORKERS=4 setsid nohup bash backtest/src/watchdog_stage5c_oos_screen.sh \
  >> backtest/output/doe/watchdog_stage5c_oos_screen.log 2>&1 < /dev/null &
echo "[session-start] Stage 5c OOS screen watchdog relaunched (pid=$!)"
