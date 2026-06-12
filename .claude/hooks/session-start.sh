#!/bin/bash
# SessionStart hook: pull latest state and relaunch Stage 4 watchdog if dead.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd /home/user/20k5ers

# Pull latest committed checkpoints from remote
git pull origin claude/awesome-maxwell-50dMF --quiet 2>/dev/null || true

# Relaunch stage4 validation watchdog if not already running
if ! ps -eo args --no-headers 2>/dev/null | grep -qF watchdog_stage4.sh; then
  VAL_WORKERS=2 \
    setsid nohup bash backtest/src/watchdog_stage4.sh \
    >> backtest/output/doe/watchdog_stage4.log 2>&1 &
  echo "[session-start] Stage 4 watchdog relaunched"
else
  echo "[session-start] Stage 4 watchdog already running"
fi
