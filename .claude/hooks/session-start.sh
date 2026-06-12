#!/bin/bash
# SessionStart hook: pull latest state and relaunch Stage 4 watchdog if dead.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd /home/user/20k5ers

# Pull latest committed checkpoints from remote
git pull origin claude/awesome-maxwell-50dMF --quiet 2>/dev/null || true

# Relaunch stage4 robustness watchdog if not already running.
# (stage4_validate is complete; robustness is the active gauntlet step.)
if [ ! -f backtest/output/doe/stage4_robustness_report.txt ] \
   || ! grep -q STAGE4_ROBUSTNESS_DONE_MARKER backtest/output/doe/stage4_robustness_run.log 2>/dev/null; then
  if ! ps -eo args --no-headers 2>/dev/null | grep -qF watchdog_stage4_robustness.sh; then
    setsid nohup bash backtest/src/watchdog_stage4_robustness.sh \
      >> backtest/output/doe/watchdog_stage4_robustness.log 2>&1 &
    echo "[session-start] Stage 4 robustness watchdog relaunched"
  else
    echo "[session-start] Stage 4 robustness watchdog already running"
  fi
else
  echo "[session-start] Stage 4 robustness already complete — nothing to relaunch"
fi
